"""UPS over Modbus TCP. Kuntur's own register map (see docs/protocolos.md), not any vendor's.

Input registers, read with function 4 from address 0:

====  ==================  ======  ==============================================
Addr  Value               Scale   Notes
====  ==================  ======  ==============================================
0     load_pct            x10
1     battery_charge_pct  x10
2     battery_temp_c      x10     signed; 0x7FFF when the sensor gives no value
3     input_voltage_v     x10     0 without grid power
4     output_voltage_v    x10
5     on_battery          0/1
6     autonomy_min        x1
7     status              bits    bit 0 battery test running, bit 1 alarm silenced
====  ==================  ======  ==============================================

Commands are written to holding register 100 (function 6): 1 starts a battery test, 2 silences the
alarm. A refusal comes back as exception 6 (busy, retry later) or 7 (not possible in this state).
"""

from __future__ import annotations

import asyncio
from typing import cast

from pymodbus.constants import ExcCodes
from pymodbus.server import ModbusTcpServer
from pymodbus.simulator import DataType, SimData, SimDevice

from kuntur_sim.models import CommandRejected, UpsModel

TELEMETRY_COUNT = 8
COMMAND_REGISTER = 100
CMD_BATTERY_TEST = 1
CMD_SILENCE_ALARM = 2
SENSOR_FAULT = 0x7FFF
STATUS_TEST_RUNNING = 1 << 0
STATUS_ALARM_SILENCED = 1 << 1
_UINT16 = 0xFFFF
_WRITE_FUNCTIONS = frozenset({6, 16})


def _u16(value: float) -> int:
    return max(0, min(_UINT16, round(value)))


def _s16(value: float) -> int:
    """Two's complement, as a signed Modbus register travels."""
    return max(-0x8000, min(0x7FFE, round(value))) & _UINT16


def encode(model: UpsModel) -> list[int]:
    status = (STATUS_TEST_RUNNING if model.test_remaining_s > 0 else 0) | (
        STATUS_ALARM_SILENCED if model.alarm_silenced else 0
    )
    temperature = _s16(model.battery_temp_c * 10) if model.temp_sensor_ok else SENSOR_FAULT
    return [
        _u16(model.load_pct * 10),
        _u16(model.battery_charge_pct * 10),
        temperature,
        _u16(model.input_voltage_v * 10),
        _u16(model.output_voltage_v * 10),
        int(model.on_battery),
        _u16(model.autonomy_min),
        status,
    ]


class UpsModbusServer:
    def __init__(self, model: UpsModel, host: str = "127.0.0.1", port: int = 0) -> None:
        self._model = model
        device = SimDevice(
            1,
            simdata=[
                SimData(0, count=TELEMETRY_COUNT, values=0, datatype=DataType.REGISTERS, readonly=True),
                SimData(COMMAND_REGISTER, count=1, values=0, datatype=DataType.REGISTERS),
            ],
            action=self._action,
        )
        self._server = ModbusTcpServer(device, address=(host, port))

    async def start(self) -> int:
        await self._server.serve_forever(background=True)
        listener = cast(asyncio.Server, self._server.transport)  # pymodbus types it as a BaseTransport
        return int(listener.sockets[0].getsockname()[1])

    async def stop(self) -> None:
        await self._server.shutdown()  # type: ignore[no-untyped-call]

    async def _action(  # noqa: PLR0917 - signature imposed by pymodbus SimAction
        self,
        function_code: int,
        start_address: int,
        address: int,
        count: int,
        registers: list[int],
        set_values: list[int] | list[bool] | None,
    ) -> ExcCodes | None:
        if set_values is None:
            offset = -start_address
            if offset >= 0 and offset + TELEMETRY_COUNT <= len(registers):
                registers[offset : offset + TELEMETRY_COUNT] = encode(self._model)
            return None
        if function_code in _WRITE_FUNCTIONS and address == COMMAND_REGISTER:
            return self._command(int(set_values[0]))
        return None

    def _command(self, code: int) -> ExcCodes | None:
        commands = {CMD_BATTERY_TEST: self._model.battery_test, CMD_SILENCE_ALARM: self._model.silence_alarm}
        command = commands.get(code)
        if command is None:
            return ExcCodes.ILLEGAL_VALUE
        try:
            command()
        except CommandRejected as exc:
            return ExcCodes.DEVICE_BUSY if exc.busy else ExcCodes.NEGATIVE_ACKNOWLEDGE
        return None
