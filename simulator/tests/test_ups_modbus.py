import random

from pymodbus.client import AsyncModbusTcpClient

from kuntur_sim.models import UpsModel
from kuntur_sim.ups_modbus import (
    CMD_BATTERY_TEST,
    COMMAND_REGISTER,
    SENSOR_FAULT,
    STATUS_TEST_RUNNING,
    TELEMETRY_COUNT,
    UpsModbusServer,
    encode,
)


def test_registers_follow_the_map_and_its_scales() -> None:
    ups = UpsModel(random.Random(1), ambient_c=31.0, base_load_pct=40.0)
    registers = encode(ups)
    assert len(registers) == TELEMETRY_COUNT
    assert (registers[0], registers[1], registers[2], registers[5]) == (400, 1000, 310, 0)


def test_a_negative_temperature_travels_as_twos_complement() -> None:
    ups = UpsModel(random.Random(1))
    ups.battery_temp_c = -5.5
    assert encode(ups)[2] == 0x10000 - 55


def test_a_silent_sensor_reads_as_the_fault_marker() -> None:
    ups = UpsModel(random.Random(1))
    ups.temp_sensor_ok = False
    assert encode(ups)[2] == SENSOR_FAULT


async def test_a_client_reads_and_commands_over_tcp() -> None:
    ups = UpsModel(random.Random(1))
    server = UpsModbusServer(ups)
    port = await server.start()
    client = AsyncModbusTcpClient("127.0.0.1", port=port, timeout=2, retries=0)
    try:
        await client.connect()
        read = await client.read_input_registers(0, count=TELEMETRY_COUNT, device_id=1)
        assert read.registers == encode(ups)

        assert not (await client.write_register(COMMAND_REGISTER, CMD_BATTERY_TEST, device_id=1)).isError()
        status = (await client.read_input_registers(7, count=1, device_id=1)).registers[0]
        assert status & STATUS_TEST_RUNNING

        busy = await client.write_register(COMMAND_REGISTER, CMD_BATTERY_TEST, device_id=1)
        unknown = await client.write_register(COMMAND_REGISTER, 99, device_id=1)
        telemetry = await client.write_register(0, 1, device_id=1)
        assert [busy.exception_code, unknown.exception_code] == [6, 3]
        assert telemetry.isError()
    finally:
        client.close()
        await server.stop()
