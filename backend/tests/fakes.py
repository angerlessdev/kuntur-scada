"""Test doubles for the ports that touch the outside world, and the application wired with them."""

from __future__ import annotations

import asyncio
import itertools
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta

from kuntur.adapters.events import InMemoryEventBus
from kuntur.adapters.persistence.memory import InMemoryStore, InMemoryUnitOfWork
from kuntur.application.acquisition import PollDevice, RecordReading
from kuntur.application.control import IssueCommand
from kuntur.application.ports import DeviceDriver, UnitOfWork
from kuntur.application.queries import FleetQueries
from kuntur.domain.commands import CommandKind
from kuntur.domain.devices import Device, DeviceKind
from kuntur.domain.events import DomainEvent
from kuntur.domain.readings import Reading
from kuntur.domain.rules import AlertEngine, AlertRule, default_rules
from tests.factories import T0


class FakeClock:
    def __init__(self, start: datetime = T0) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, delta: timedelta) -> None:
        self.current += delta


class SequentialIds:
    def __init__(self) -> None:
        self._counter = itertools.count(1)

    def new_id(self) -> str:
        return f"id-{next(self._counter)}"


class RecordingBus(InMemoryEventBus):
    """Event bus that also keeps every published event for assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.events: list[DomainEvent] = []
        self.subscribe(self.events.append)

    def of_type[E: DomainEvent](self, kind: type[E]) -> list[E]:
        return [e for e in self.events if isinstance(e, kind)]


@dataclass
class ScriptedDriver:
    """Plays back prepared readings (or exceptions) and records the commands it receives.
    ``on_execute`` lets a test look at the world while the device is busy with a command."""

    readings: deque[Reading | Exception] = field(default_factory=deque)
    command_results: deque[str | Exception] = field(default_factory=deque)
    delay_s: float = 0.0
    executed: list[tuple[str, CommandKind]] = field(default_factory=list)
    on_execute: Callable[[], None] | None = None

    async def read(self, device: Device, at: datetime) -> Reading:
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        item = self.readings.popleft()
        if isinstance(item, Exception):
            raise item
        return item

    async def execute(self, device: Device, command: CommandKind) -> str:
        self.executed.append((device.id, command))
        if self.on_execute is not None:
            self.on_execute()
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        result = self.command_results.popleft() if self.command_results else "Ejecutado"
        if isinstance(result, Exception):
            raise result
        return result


class SingleDriverRegistry:
    def __init__(self, driver: DeviceDriver) -> None:
        self.driver = driver

    def for_kind(self, kind: DeviceKind) -> DeviceDriver:
        return self.driver


@dataclass
class App:
    """The application wired with in-memory adapters, the way the composition root wires it."""

    store: InMemoryStore
    clock: FakeClock
    bus: RecordingBus
    driver: ScriptedDriver
    record: RecordReading
    poll: PollDevice
    issue: IssueCommand
    queries: FleetQueries

    def uow(self) -> UnitOfWork:
        return InMemoryUnitOfWork(self.store)


def build_app(
    *devices: Device, rules: Sequence[AlertRule] | None = None, timeout_s: float = 1.0, start: datetime = T0
) -> App:
    store = InMemoryStore()
    for device in devices:
        store.devices[device.id] = replace(device)

    def uow_factory() -> UnitOfWork:
        return InMemoryUnitOfWork(store)

    clock, ids, bus, driver = FakeClock(start), SequentialIds(), RecordingBus(), ScriptedDriver()
    drivers = SingleDriverRegistry(driver)
    engine = AlertEngine(default_rules() if rules is None else tuple(rules))
    record = RecordReading(uow_factory, engine, bus, ids)
    return App(
        store=store,
        clock=clock,
        bus=bus,
        driver=driver,
        record=record,
        poll=PollDevice(drivers, record, clock, timeout_s),
        issue=IssueCommand(uow_factory, drivers, clock, ids, bus, timeout_s),
        queries=FleetQueries(uow_factory, clock),
    )
