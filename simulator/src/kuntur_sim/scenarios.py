"""Scripted incidents. Each one says which alert the platform should raise, or that it should stay
quiet: the simulator records them as ground truth to measure the alerts' precision and recall."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kuntur_sim.faults import FaultConfig, FaultMode
from kuntur_sim.fleet import Kind

if TYPE_CHECKING:
    from kuntur_sim.simulator import Simulator

Story = Callable[["Simulator", str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class Scenario:
    name: str
    description: str
    kinds: frozenset[Kind]
    expected_alert: str | None
    """The alert code the platform should raise, or ``None`` when raising one would be a false alarm."""
    story: Story


def network(mode: FaultMode, seconds: float, **options: float) -> Story:
    async def story(sim: Simulator, device_id: str) -> None:
        await sim.set_fault(device_id, FaultConfig(mode, **options))
        try:
            await asyncio.sleep(seconds)
        finally:
            await sim.set_fault(device_id, FaultConfig())

    return story


def conditions(seconds: float, **changes: Any) -> Story:
    async def story(sim: Simulator, device_id: str) -> None:
        before = {
            name: value for name, value in sim.device(device_id).conditions().items() if name in changes
        }
        sim.set_conditions(device_id, changes)
        try:
            await asyncio.sleep(seconds)
        finally:
            sim.set_conditions(device_id, before)

    return story


def clock_jump(offset_s: float, seconds: float) -> Story:
    async def story(sim: Simulator, device_id: str) -> None:
        start = sim.device(device_id).conditions()["clock_offset_s"]
        sim.set_conditions(device_id, {"clock_offset_s": start + offset_s})
        try:
            await asyncio.sleep(seconds)
        finally:
            sim.set_conditions(device_id, {"clock_offset_s": start})

    return story


async def _impact(sim: Simulator, device_id: str) -> None:
    sim.impact(device_id)


ALL_KINDS = frozenset(Kind)

SCENARIOS: dict[str, Scenario] = {
    scenario.name: scenario
    for scenario in (
        Scenario(
            "equipo-caido",
            "El equipo deja de responder durante 60 s, como sin energía o sin red.",
            ALL_KINDS,
            "DEVICE_UNREACHABLE",
            network(FaultMode.DOWN, 60),
        ),
        Scenario(
            "perdida-aislada",
            "Se pierde una sola lectura (4 s sin respuesta). No debe haber alarma.",
            ALL_KINDS,
            None,
            network(FaultMode.DOWN, 4),
        ),
        Scenario(
            "sin-respuesta",
            "El equipo acepta la conexión pero no contesta durante 60 s.",
            ALL_KINDS,
            "DEVICE_UNREACHABLE",
            network(FaultMode.TIMEOUT, 60),
        ),
        Scenario(
            "enlace-lento",
            "Cada respuesta tarda 2 s durante 60 s. Lento no es caído: no debe haber alarma.",
            ALL_KINDS,
            None,
            network(FaultMode.SLOW, 60, delay_s=2),
        ),
        Scenario(
            "red-inestable",
            "La conexión se corta y vuelve cada 20 s durante 2 minutos.",
            ALL_KINDS,
            "DEVICE_UNREACHABLE",
            network(FaultMode.FLAPPING, 120, period_s=20),
        ),
        Scenario(
            "corte-de-energia",
            "Se corta la red eléctrica 90 s y el UPS pasa a batería.",
            frozenset({Kind.UPS}),
            "UPS_ON_BATTERY",
            conditions(90, grid_ok=False),
        ),
        Scenario(
            "bateria-caliente",
            "La sala eléctrica sube a 48 °C durante 4 minutos.",
            frozenset({Kind.UPS}),
            "UPS_BATTERY_HOT",
            conditions(240, ambient_c=48),
        ),
        Scenario(
            "sensor-sin-dato",
            "El sensor de temperatura deja de dar valor 60 s: lectura parcial, amarillo, sin alarma.",
            frozenset({Kind.UPS}),
            None,
            conditions(60, temp_sensor_ok=False),
        ),
        Scenario(
            "impacto",
            "Un vehículo golpea la barrera.",
            frozenset({Kind.BARRIER}),
            "BARRIER_IMPACT",
            _impact,
        ),
        Scenario(
            "reloj-desfasado",
            "El reloj de la cámara se adelanta 10 minutos durante 3 minutos.",
            frozenset({Kind.CAMERA}),
            "CAMERA_CLOCK_DRIFT",
            clock_jump(600, 180),
        ),
    )
}
