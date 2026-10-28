"""The simulator: one model, one protocol server and one fault proxy per declared device."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import random
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Protocol

from kuntur_sim.barrier_ws import BarrierWebSocketServer
from kuntur_sim.camera_http import create_camera_app
from kuntur_sim.digest import DigestVerifier
from kuntur_sim.faults import FaultConfig, FaultProxy
from kuntur_sim.fleet import DeviceSpec, Kind
from kuntur_sim.models import BarrierModel, CameraModel, UpsModel
from kuntur_sim.servers import HttpServer
from kuntur_sim.ups_modbus import UpsModbusServer

if TYPE_CHECKING:
    from kuntur_sim.scenarios import Scenario

logger = logging.getLogger(__name__)

Model = UpsModel | BarrierModel | CameraModel

INITIAL_CONDITIONS: Mapping[Kind, frozenset[str]] = {
    Kind.UPS: frozenset({"ambient_c", "base_load_pct"}),
    Kind.BARRIER: frozenset({"traffic_per_min", "cycles_total", "impacts_total", "ambient_c"}),
    Kind.CAMERA: frozenset({"clock_offset_s", "drift_s_per_hour", "ambient_c"}),
}
"""What the ``sim`` section of the fleet file may set, per kind."""

CONDITIONS: Mapping[Kind, Mapping[str, type]] = {
    Kind.UPS: {"grid_ok": bool, "ambient_c": float, "base_load_pct": float, "temp_sensor_ok": bool},
    Kind.BARRIER: {"traffic_per_min": float, "faulted": bool, "ambient_c": float},
    Kind.CAMERA: {"clock_offset_s": float, "recording": bool, "ambient_c": float},
}
"""What the control API may change at run time, per kind."""


class Stoppable(Protocol):
    async def stop(self) -> None: ...


@dataclass
class SimulatedDevice:
    spec: DeviceSpec
    model: Model
    proxy: FaultProxy | None = None

    def conditions(self) -> dict[str, Any]:
        return {name: getattr(self.model, name) for name in CONDITIONS[self.spec.kind]}


@dataclass(frozen=True, slots=True)
class Incident:
    """Ground truth: what was injected, when, and which alert the platform should raise (if any)."""

    scenario: str
    device_id: str
    expected_alert: str | None
    started_at: datetime
    ended_at: datetime | None = None


def build_model(spec: DeviceSpec, rng: random.Random) -> Model:
    unknown = set(spec.sim) - INITIAL_CONDITIONS[spec.kind]
    if unknown:
        raise ValueError(f"{spec.id}: unknown sim settings {sorted(unknown)}")
    sim = spec.sim
    if spec.kind is Kind.UPS:
        return UpsModel(
            rng, ambient_c=sim.get("ambient_c", 25.0), base_load_pct=sim.get("base_load_pct", 40.0)
        )
    if spec.kind is Kind.BARRIER:
        return BarrierModel(
            rng,
            traffic_per_min=sim.get("traffic_per_min", 4.0),
            cycles_total=int(sim.get("cycles_total", 0)),
            impacts_total=int(sim.get("impacts_total", 0)),
            ambient_c=sim.get("ambient_c", 22.0),
        )
    return CameraModel(
        rng,
        clock_offset_s=sim.get("clock_offset_s", 0.0),
        drift_s_per_hour=sim.get("drift_s_per_hour", 0.3),
        ambient_c=sim.get("ambient_c", 24.0),
    )


class Simulator:
    def __init__(
        self,
        specs: Sequence[DeviceSpec],
        *,
        camera_user: str,
        camera_password: str,
        bind_host: str = "0.0.0.0",  # noqa: S104 - a simulator in a container must be reachable
        seed: int = 2026,
        tick_s: float = 1.0,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.devices = {
            spec.id: SimulatedDevice(spec, build_model(spec, random.Random(f"{seed}:{spec.id}")))
            for spec in specs
        }
        self.incidents: list[Incident] = []
        self.clock = clock
        self._bind_host = bind_host
        self._tick_s = tick_s
        self._verifier = DigestVerifier("kuntur-camera", camera_user, camera_password)
        self._servers: list[Stoppable] = []
        self._ticker: asyncio.Task[None] | None = None
        self._running: dict[str, tuple[str, asyncio.Task[None]]] = {}

    def device(self, device_id: str) -> SimulatedDevice:
        try:
            return self.devices[device_id]
        except KeyError:
            raise KeyError(f"Unknown device {device_id}") from None

    async def start(self, *, ticking: bool = True) -> None:
        cameras = {d.spec.id: d.model for d in self.devices.values() if isinstance(d.model, CameraModel)}
        camera_port = 0
        if cameras:
            camera_server = HttpServer(create_camera_app(cameras, self._verifier, self.clock), "127.0.0.1", 0)
            camera_port = await camera_server.start()
            self._servers.append(camera_server)
        for device in self.devices.values():
            internal_port = camera_port
            if isinstance(device.model, UpsModel):
                ups = UpsModbusServer(device.model)
                internal_port = await ups.start()
                self._servers.append(ups)
            elif isinstance(device.model, BarrierModel):
                barrier = BarrierWebSocketServer(device.model)
                internal_port = await barrier.start()
                self._servers.append(barrier)
            device.proxy = FaultProxy(
                device.spec.id, (self._bind_host, device.spec.port), ("127.0.0.1", internal_port)
            )
            await device.proxy.start()
        if ticking:
            self._ticker = asyncio.create_task(self._tick_forever(), name="sim-ticker")
        logger.info("Simulating %d devices", len(self.devices))

    async def stop(self) -> None:
        tasks = [t for t in (self._ticker, *(task for _, task in self._running.values())) if t is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError):
                await task
        for device in self.devices.values():
            if device.proxy is not None:
                await device.proxy.stop()
        for server in reversed(self._servers):
            await server.stop()
        self._servers.clear()

    def tick(self, dt: float) -> None:
        for device in self.devices.values():
            device.model.tick(dt)

    async def _tick_forever(self) -> None:
        while True:
            await asyncio.sleep(self._tick_s)
            self.tick(self._tick_s)

    async def set_fault(self, device_id: str, config: FaultConfig) -> None:
        proxy = self.device(device_id).proxy
        if proxy is None:
            raise RuntimeError("The simulator is not running")
        await proxy.apply(config)

    def set_conditions(self, device_id: str, changes: Mapping[str, object]) -> dict[str, Any]:
        device = self.device(device_id)
        allowed = CONDITIONS[device.spec.kind]
        unknown = set(changes) - set(allowed)
        if unknown:
            raise ValueError(f"{sorted(unknown)} do not apply to a {device.spec.kind}")
        for name, value in changes.items():
            setattr(device.model, name, allowed[name](value))
        return device.conditions()

    def impact(self, device_id: str) -> int:
        model = self.device(device_id).model
        if not isinstance(model, BarrierModel):
            raise ValueError(f"{device_id} is not a barrier")
        model.impact()
        return model.impacts_total

    def running_scenario(self, device_id: str) -> str | None:
        running = self._running.get(device_id)
        return running[0] if running is not None and not running[1].done() else None

    def describe(self, device: SimulatedDevice) -> dict[str, Any]:
        fault = device.proxy.config if device.proxy is not None else FaultConfig()
        return {
            "id": device.spec.id,
            "kind": device.spec.kind,
            "port": device.proxy.port if device.proxy is not None else device.spec.port,
            "fault": {"mode": fault.mode, "delay_s": fault.delay_s, "period_s": fault.period_s},
            "conditions": device.conditions(),
            "scenario": self.running_scenario(device.spec.id),
        }

    def run_scenario(self, scenario: Scenario, device_id: str) -> Incident:
        """Plays a scenario in the background and records it as ground truth. One per device at a time."""
        device = self.device(device_id)
        if device.spec.kind not in scenario.kinds:
            raise ValueError(f"{scenario.name} does not apply to a {device.spec.kind}")
        busy = self.running_scenario(device_id)
        if busy is not None:
            raise RuntimeError(f"{device_id} is already running {busy}")
        index = len(self.incidents)
        self.incidents.append(Incident(scenario.name, device_id, scenario.expected_alert, self.clock()))

        async def play() -> None:
            try:
                await scenario.story(self, device_id)
            finally:
                self.incidents[index] = replace(self.incidents[index], ended_at=self.clock())

        self._running[device_id] = (
            scenario.name,
            asyncio.create_task(play(), name=f"{scenario.name}-{device_id}"),
        )
        return self.incidents[index]
