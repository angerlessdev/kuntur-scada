"""Composition root: the only place that knows every concrete adapter and wires them together."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from datetime import timedelta

from kuntur.adapters.drivers.barrier_websocket import WebSocketBarrierDriver
from kuntur.adapters.drivers.camera_http import HttpCameraDriver
from kuntur.adapters.drivers.registry import StaticDriverRegistry
from kuntur.adapters.drivers.ups_modbus import ModbusUpsDriver
from kuntur.adapters.events import InMemoryEventBus
from kuntur.adapters.fleet_file import load_fleet
from kuntur.adapters.live import LiveHub
from kuntur.adapters.metrics import Metrics
from kuntur.adapters.narrators.claude import ClaudeNarrator
from kuntur.adapters.narrators.template import TemplateNarrator
from kuntur.adapters.persistence.memory import InMemoryStore, InMemoryUnitOfWork
from kuntur.adapters.persistence.sql.database import create_sql_engine
from kuntur.adapters.persistence.sql.unit_of_work import SqlUnitOfWork
from kuntur.adapters.security import Argon2PasswordHasher, JwtTokenService
from kuntur.adapters.system import SystemClock, UuidGenerator
from kuntur.application.acquisition import PollDevice, RecordReading
from kuntur.application.collector import Collector
from kuntur.application.control import IssueCommand
from kuntur.application.explain import ExplainAlert
from kuntur.application.fleet import sync_fleet
from kuntur.application.identity import Authenticate, LoginLimiter, ResolveActor, ensure_accounts
from kuntur.application.ports import (
    Clock,
    DriverRegistry,
    IncidentNarrator,
    PasswordHasher,
    UnitOfWork,
    UnitOfWorkFactory,
)
from kuntur.application.queries import FleetQueries
from kuntur.config import Settings
from kuntur.domain.alerts import AlertState
from kuntur.domain.devices import Device, DeviceKind
from kuntur.domain.rules import AlertEngine, default_rules
from kuntur.domain.security import Role

logger = logging.getLogger(__name__)

Closer = Callable[[], Awaitable[None]]


class ConfigurationError(ValueError):
    """The settings cannot run the platform. The message names the variable to set."""


@dataclass
class Application:
    settings: Settings
    uow_factory: UnitOfWorkFactory
    bus: InMemoryEventBus
    clock: Clock
    hasher: PasswordHasher
    record: RecordReading
    poll: PollDevice
    issue: IssueCommand
    queries: FleetQueries
    authenticate: Authenticate
    resolve_actor: ResolveActor
    collector: Collector
    explain: ExplainAlert
    hub: LiveHub
    metrics: Metrics
    fleet: Sequence[Device]
    closers: list[Closer] = field(default_factory=list)
    _stop: asyncio.Event = field(default_factory=asyncio.Event)
    _collector_task: asyncio.Task[None] | None = None

    def accounts(self) -> dict[str, tuple[Role, str]]:
        declared = {"operador": (Role.OPERATOR, self.settings.operator_password)}
        declared["visitante"] = (Role.VIEWER, self.settings.viewer_password)
        return {
            name: (role, secret.get_secret_value()) for name, (role, secret) in declared.items() if secret
        }

    async def start(self) -> None:
        report = await asyncio.to_thread(sync_fleet, self.uow_factory, self.fleet)
        logger.info("Fleet: %d added, %d updated, %d retired", report.added, report.updated, report.retired)
        await asyncio.to_thread(ensure_accounts, self.uow_factory, self.hasher, self.accounts())
        active = await asyncio.to_thread(
            self.queries.alerts, state=AlertState.ACTIVE, device_id=None, limit=10_000
        )
        self.metrics.start_from(active)
        self.hub.bind(asyncio.get_running_loop())
        if self.settings.collector_enabled:
            self._stop.clear()
            self._collector_task = asyncio.create_task(
                self.collector.run_forever(self._stop), name="collector"
            )

    async def stop(self) -> None:
        self._stop.set()
        if self._collector_task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._collector_task
            self._collector_task = None
        self.hub.unbind()
        for close in reversed(self.closers):
            await close()


def _drivers(settings: Settings, fleet: Sequence[Device], closers: list[Closer]) -> DriverRegistry:
    has_cameras = any(device.kind is DeviceKind.CAMERA for device in fleet)
    if has_cameras and settings.camera_password is None:
        raise ConfigurationError("The fleet has cameras: set KUNTUR_CAMERA_PASSWORD")
    password = settings.camera_password.get_secret_value() if settings.camera_password else ""
    camera = HttpCameraDriver(settings.camera_user, password, timeout_s=settings.driver_timeout_s)
    closers.append(camera.aclose)
    return StaticDriverRegistry(
        {
            DeviceKind.UPS: ModbusUpsDriver(timeout_s=settings.driver_timeout_s),
            DeviceKind.BARRIER: WebSocketBarrierDriver(timeout_s=settings.driver_timeout_s),
            DeviceKind.CAMERA: camera,
        }
    )


def _unit_of_work(settings: Settings, closers: list[Closer]) -> UnitOfWorkFactory:
    if settings.database_url is None:
        logger.warning("KUNTUR_DATABASE_URL is not set: data lives in memory and is lost on exit")
        store = InMemoryStore()

        def memory() -> UnitOfWork:
            return InMemoryUnitOfWork(store)

        return memory
    engine = create_sql_engine(settings.database_url.get_secret_value())

    async def dispose() -> None:
        await asyncio.to_thread(engine.dispose)

    closers.append(dispose)

    def sql() -> UnitOfWork:
        return SqlUnitOfWork(engine)

    return sql


def _narrator(settings: Settings, closers: list[Closer]) -> IncidentNarrator:
    template = TemplateNarrator()
    if settings.ai_provider == "template":
        return template
    import anthropic  # noqa: PLC0415 - only needed when Claude explains the alerts

    key = settings.anthropic_api_key.get_secret_value() if settings.anthropic_api_key else None
    client = anthropic.AsyncAnthropic(
        api_key=key, timeout=anthropic.Timeout(settings.ai_timeout_s, connect=5.0), max_retries=1
    )
    closers.append(client.close)
    return ClaudeNarrator(client, model=settings.ai_model, effort=settings.ai_effort)


def build_application(
    settings: Settings,
    *,
    drivers: DriverRegistry | None = None,
    clock: Clock | None = None,
    fleet: Sequence[Device] | None = None,
) -> Application:
    if settings.token_secret is None:
        raise ConfigurationError("Set KUNTUR_TOKEN_SECRET (32 bytes or more) to sign the sessions")
    closers: list[Closer] = []
    clock = clock or SystemClock()
    fleet = list(fleet) if fleet is not None else load_fleet(settings.fleet_file)
    uow_factory = _unit_of_work(settings, closers)
    drivers = drivers or _drivers(settings, fleet, closers)

    bus, metrics, hub = InMemoryEventBus(), Metrics(), LiveHub()
    bus.subscribe(metrics.handle)
    bus.subscribe(hub.handle)
    ids = UuidGenerator()
    record = RecordReading(uow_factory, AlertEngine(default_rules()), bus, ids)
    poll = PollDevice(drivers, record, clock, settings.poll_timeout_s)
    hasher = Argon2PasswordHasher()
    tokens = JwtTokenService(
        settings.token_secret.get_secret_value(), timedelta(minutes=settings.token_ttl_minutes)
    )
    return Application(
        settings=settings,
        uow_factory=uow_factory,
        bus=bus,
        clock=clock,
        hasher=hasher,
        record=record,
        poll=poll,
        issue=IssueCommand(uow_factory, drivers, clock, ids, bus, settings.poll_timeout_s),
        queries=FleetQueries(uow_factory, clock),
        authenticate=Authenticate(uow_factory, hasher, tokens, LoginLimiter(SystemClock())),
        resolve_actor=ResolveActor(uow_factory, tokens),
        collector=Collector(poll, uow_factory, settings.poll_interval_s, settings.max_concurrent_polls),
        explain=ExplainAlert(
            uow_factory,
            _narrator(settings, closers),
            TemplateNarrator(),
            clock,
            budget_s=2 * settings.ai_timeout_s + 5,
        ),
        hub=hub,
        metrics=metrics,
        fleet=fleet,
        closers=closers,
    )
