"""The real drivers against the real simulator, over real sockets, with network faults injected."""

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from kuntur_sim.faults import FaultConfig, FaultMode
from kuntur_sim.fleet import DeviceSpec, Kind
from kuntur_sim.models import UpsModel
from kuntur_sim.simulator import Simulator
from kuntur_sim.ups_modbus import encode

from kuntur.adapters.drivers.barrier_websocket import WebSocketBarrierDriver
from kuntur.adapters.drivers.camera_http import HttpCameraDriver
from kuntur.adapters.drivers.modbus_tcp import read_input_registers
from kuntur.adapters.drivers.ups_modbus import ModbusUpsDriver
from kuntur.application.ports import CommandExecutionError, DeviceDriver
from kuntur.domain.commands import CommandKind
from kuntur.domain.devices import Device, Endpoint
from kuntur.domain.readings import FailureCause, ReadingStatus
from tests.factories import T0, barrier, camera, ups

pytestmark = pytest.mark.integration

PASSWORD = "clave-de-integracion"


@pytest.fixture
async def sim() -> AsyncIterator[Simulator]:
    specs = [
        DeviceSpec("ups-01", Kind.UPS, 0),
        DeviceSpec("barrera-01", Kind.BARRIER, 0),
        DeviceSpec("camara-01", Kind.CAMERA, 0, "/cameras/camara-01"),
    ]
    simulator = Simulator(specs, camera_user="admin", camera_password=PASSWORD, bind_host="127.0.0.1")
    await simulator.start(ticking=False)
    yield simulator
    await simulator.stop()


@pytest.fixture
async def camera_driver() -> AsyncIterator[HttpCameraDriver]:
    driver = HttpCameraDriver("admin", PASSWORD, timeout_s=3)
    yield driver
    await driver.aclose()


def located(sim: Simulator, device: Device) -> Device:
    """The device as declared, but pointing at the port the simulator's proxy got."""
    proxy = sim.device(device.id).proxy
    assert proxy is not None
    return replace(device, endpoint=Endpoint("127.0.0.1", proxy.port, device.endpoint.path))


class TestUps:
    async def test_our_modbus_client_and_pymodbus_agree_on_every_register(self, sim: Simulator) -> None:
        device = located(sim, ups())
        model = sim.device("ups-01").model
        assert isinstance(model, UpsModel)
        registers = await read_input_registers(
            device.endpoint.host, device.endpoint.port, unit=1, address=0, count=8, timeout_s=3
        )
        assert registers == encode(model)

    async def test_a_reading_carries_the_models_state(self, sim: Simulator) -> None:
        reading = await ModbusUpsDriver().read(located(sim, ups()), T0)
        assert reading.status is ReadingStatus.OK
        assert reading.metric("battery_charge_pct") == 100
        assert reading.metric("on_battery") == 0

    async def test_a_silent_sensor_arrives_as_a_partial_reading(self, sim: Simulator) -> None:
        sim.set_conditions("ups-01", {"temp_sensor_ok": False})
        reading = await ModbusUpsDriver().read(located(sim, ups()), T0)
        assert (reading.status, reading.cause) == (ReadingStatus.PARTIAL, FailureCause.INVALID_DATA)

    async def test_the_device_refuses_a_second_battery_test(self, sim: Simulator) -> None:
        driver, device = ModbusUpsDriver(), located(sim, ups())
        assert await driver.execute(device, CommandKind.UPS_BATTERY_TEST) == "Prueba de batería iniciada"
        with pytest.raises(CommandExecutionError, match="ocupado"):
            await driver.execute(device, CommandKind.UPS_BATTERY_TEST)

    async def test_slow_is_not_down(self, sim: Simulator) -> None:
        device = located(sim, ups())
        await sim.set_fault("ups-01", FaultConfig(FaultMode.SLOW, delay_s=0.4))
        assert (await ModbusUpsDriver(timeout_s=3).read(device, T0)).status is ReadingStatus.OK


class TestBarrier:
    async def test_a_reading_and_a_command(self, sim: Simulator) -> None:
        driver, device = WebSocketBarrierDriver(), located(sim, barrier())
        reading = await driver.read(device, T0)
        assert reading.status is ReadingStatus.OK
        assert reading.metric("open") == 0
        assert await driver.execute(device, CommandKind.BARRIER_OPEN) == "Barrera abierta"
        assert (await driver.read(device, T0)).metric("open") == 1

    async def test_a_faulted_barrier_answers_but_says_so(self, sim: Simulator) -> None:
        sim.set_conditions("barrera-01", {"faulted": True})
        driver, device = WebSocketBarrierDriver(), located(sim, barrier())
        assert (await driver.read(device, T0)).cause is FailureCause.DEVICE_FAULT
        with pytest.raises(CommandExecutionError, match="falla"):
            await driver.execute(device, CommandKind.BARRIER_OPEN)


class TestCamera:
    async def test_the_drift_is_read_through_digest_auth(
        self, sim: Simulator, camera_driver: HttpCameraDriver
    ) -> None:
        sim.set_conditions("camara-01", {"clock_offset_s": 600})
        reading = await camera_driver.read(located(sim, camera()), datetime.now(UTC))
        assert reading.status is ReadingStatus.OK, reading.detail
        assert reading.metric("clock_drift_s") == pytest.approx(600, abs=0.5)

    async def test_wrong_credentials_are_an_auth_failure(self, sim: Simulator) -> None:
        driver = HttpCameraDriver("admin", "otra-clave")
        try:
            assert (await driver.read(located(sim, camera()), T0)).cause is FailureCause.AUTH_FAILED
        finally:
            await driver.aclose()

    async def test_a_reboot_answers_then_the_camera_is_unavailable(
        self, sim: Simulator, camera_driver: HttpCameraDriver
    ) -> None:
        device = located(sim, camera())
        assert await camera_driver.execute(device, CommandKind.CAMERA_REBOOT) == "Reinicio en curso"
        assert (await camera_driver.read(device, T0)).cause is FailureCause.DEVICE_FAULT
        with pytest.raises(CommandExecutionError, match="reiniciando"):
            await camera_driver.execute(device, CommandKind.CAMERA_REBOOT)


@pytest.mark.parametrize(
    ("mode", "timeout_s", "cause"),
    [(FaultMode.DOWN, 5.0, FailureCause.CONNECTION_REFUSED), (FaultMode.TIMEOUT, 0.5, FailureCause.TIMEOUT)],
)
async def test_every_driver_classifies_the_same_network_fault_the_same_way(
    sim: Simulator, mode: FaultMode, timeout_s: float, cause: FailureCause
) -> None:
    camera_reader = HttpCameraDriver("admin", PASSWORD, timeout_s=timeout_s)
    drivers: list[tuple[DeviceDriver, Device]] = [
        (ModbusUpsDriver(timeout_s=timeout_s), ups()),
        (WebSocketBarrierDriver(timeout_s=timeout_s), barrier()),
        (camera_reader, camera()),
    ]
    try:
        for driver, declared in drivers:
            device = located(sim, declared)
            await sim.set_fault(device.id, FaultConfig(mode))
            reading = await driver.read(device, T0)
            assert (reading.status, reading.cause) == (ReadingStatus.FAILED, cause), (
                device.id,
                reading.detail,
            )
    finally:
        await camera_reader.aclose()
