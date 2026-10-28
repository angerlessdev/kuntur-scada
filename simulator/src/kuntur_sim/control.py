"""Control API: inject faults, change field conditions and play scenarios while the platform watches."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from kuntur_sim.faults import FaultConfig, FaultMode
from kuntur_sim.scenarios import SCENARIOS
from kuntur_sim.simulator import Incident, Simulator


class FaultIn(BaseModel):
    mode: FaultMode
    delay_s: float = Field(3.0, ge=0, le=60, description="Retardo de cada respuesta en modo SLOW")
    period_s: float = Field(15.0, gt=0, le=600, description="Semiperiodo de corte en modo FLAPPING")


class ConditionsIn(BaseModel):
    """Only the fields that apply to the device's kind are accepted."""

    model_config = ConfigDict(extra="forbid")

    grid_ok: bool | None = None
    ambient_c: float | None = Field(None, ge=-20, le=80)
    base_load_pct: float | None = Field(None, ge=0, le=100)
    temp_sensor_ok: bool | None = None
    traffic_per_min: float | None = Field(None, ge=0, le=60)
    faulted: bool | None = None
    clock_offset_s: float | None = Field(None, ge=-86_400, le=86_400)
    recording: bool | None = None


class ScenarioIn(BaseModel):
    device_id: str


def _incident(incident: Incident) -> dict[str, Any]:
    return {
        "scenario": incident.scenario,
        "device_id": incident.device_id,
        "expected_alert": incident.expected_alert,
        "started_at": incident.started_at.isoformat(),
        "ended_at": incident.ended_at.isoformat() if incident.ended_at else None,
    }


def create_control_app(sim: Simulator) -> FastAPI:
    app = FastAPI(
        title="Kuntur SCADA — simulador de campo",
        version="0.1.0",
        description="Inyecta fallas de red, cambia las condiciones de campo y reproduce incidentes.",
    )

    def known(device_id: str) -> None:
        if device_id not in sim.devices:
            raise HTTPException(404, f"Equipo desconocido: {device_id}")

    @app.get("/sim/devices")
    async def devices() -> list[dict[str, Any]]:
        return [sim.describe(device) for device in sim.devices.values()]

    @app.put("/sim/devices/{device_id}/fault")
    async def set_fault(device_id: str, fault: FaultIn) -> dict[str, Any]:
        known(device_id)
        await sim.set_fault(device_id, FaultConfig(fault.mode, fault.delay_s, fault.period_s))
        return sim.describe(sim.device(device_id))

    @app.patch("/sim/devices/{device_id}/conditions")
    async def set_conditions(device_id: str, changes: ConditionsIn) -> dict[str, Any]:
        known(device_id)
        try:
            return sim.set_conditions(device_id, changes.model_dump(exclude_none=True))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.post("/sim/devices/{device_id}/impact")
    async def impact(device_id: str) -> dict[str, int]:
        known(device_id)
        try:
            return {"impacts_total": sim.impact(device_id)}
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/sim/scenarios")
    async def scenarios() -> list[dict[str, Any]]:
        return [
            {
                "name": s.name,
                "description": s.description,
                "kinds": sorted(s.kinds),
                "expected_alert": s.expected_alert,
            }
            for s in SCENARIOS.values()
        ]

    @app.post("/sim/scenarios/{name}", status_code=202)
    async def run_scenario(name: str, body: ScenarioIn) -> dict[str, Any]:
        scenario = SCENARIOS.get(name)
        if scenario is None:
            raise HTTPException(404, f"Escenario desconocido: {name}")
        known(body.device_id)
        try:
            return _incident(sim.run_scenario(scenario, body.device_id))
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.get("/sim/incidents")
    async def incidents() -> list[dict[str, Any]]:
        return [_incident(incident) for incident in sim.incidents]

    return app
