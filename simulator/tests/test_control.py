import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest

from kuntur_sim.control import create_control_app
from kuntur_sim.faults import FaultMode
from kuntur_sim.fleet import DeviceSpec, Kind
from kuntur_sim.simulator import Simulator


@pytest.fixture
async def sim() -> AsyncIterator[Simulator]:
    specs = [
        DeviceSpec("ups-1", Kind.UPS, 0),
        DeviceSpec("barrera-1", Kind.BARRIER, 0),
        DeviceSpec("camara-1", Kind.CAMERA, 0, "/cameras/camara-1"),
    ]
    simulator = Simulator(specs, camera_user="admin", camera_password="clave", bind_host="127.0.0.1")
    await simulator.start(ticking=False)
    yield simulator
    await simulator.stop()


@pytest.fixture
async def client(sim: Simulator) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=create_control_app(sim))
    async with httpx.AsyncClient(transport=transport, base_url="http://sim") as client:
        yield client


async def test_lists_every_device_with_its_real_port(client: httpx.AsyncClient) -> None:
    devices = (await client.get("/sim/devices")).json()
    assert [d["id"] for d in devices] == ["ups-1", "barrera-1", "camara-1"]
    assert all(d["port"] > 0 for d in devices)


async def test_a_fault_reaches_the_proxy(client: httpx.AsyncClient, sim: Simulator) -> None:
    response = await client.put("/sim/devices/ups-1/fault", json={"mode": "TIMEOUT"})
    assert response.json()["fault"]["mode"] == "TIMEOUT"
    proxy = sim.device("ups-1").proxy
    assert proxy is not None
    assert proxy.config.mode is FaultMode.TIMEOUT


async def test_conditions_must_belong_to_the_kind(client: httpx.AsyncClient) -> None:
    assert (await client.patch("/sim/devices/ups-1/conditions", json={"grid_ok": False})).json()[
        "grid_ok"
    ] is False
    assert (
        await client.patch("/sim/devices/camara-1/conditions", json={"grid_ok": False})
    ).status_code == 422
    assert (await client.patch("/sim/devices/ups-1/conditions", json={"voltaje": 3})).status_code == 422
    assert (await client.patch("/sim/devices/nadie/conditions", json={})).status_code == 404


async def test_an_impact_is_only_for_barriers(client: httpx.AsyncClient) -> None:
    assert (await client.post("/sim/devices/barrera-1/impact")).json() == {"impacts_total": 1}
    assert (await client.post("/sim/devices/ups-1/impact")).status_code == 422


async def test_a_scenario_is_recorded_as_ground_truth(client: httpx.AsyncClient) -> None:
    started = await client.post("/sim/scenarios/impacto", json={"device_id": "barrera-1"})
    assert started.status_code == 202
    assert started.json()["expected_alert"] == "BARRIER_IMPACT"
    await asyncio.sleep(0.05)
    [incident] = (await client.get("/sim/incidents")).json()
    assert incident["ended_at"] is not None


async def test_one_scenario_at_a_time_per_device(client: httpx.AsyncClient) -> None:
    assert (await client.post("/sim/scenarios/equipo-caido", json={"device_id": "ups-1"})).status_code == 202
    assert (
        await client.post("/sim/scenarios/corte-de-energia", json={"device_id": "ups-1"})
    ).status_code == 409


async def test_a_scenario_must_fit_the_device(client: httpx.AsyncClient) -> None:
    assert (await client.post("/sim/scenarios/impacto", json={"device_id": "ups-1"})).status_code == 422
    assert (await client.post("/sim/scenarios/no-existe", json={"device_id": "ups-1"})).status_code == 404
