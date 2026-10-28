"""UPS over Modbus TCP, with Kuntur's register map (see docs/protocolos.md)."""

from __future__ import annotations

import logging
from datetime import datetime

from kuntur.adapters.drivers.decoding import assemble
from kuntur.adapters.drivers.failures import classify
from kuntur.adapters.drivers.modbus_tcp import ModbusExceptionResponse, read_input_registers, write_register
from kuntur.application.ports import CommandExecutionError
from kuntur.domain.commands import CommandKind
from kuntur.domain.devices import Device
from kuntur.domain.readings import FailureCause, Reading

logger = logging.getLogger(__name__)

TELEMETRY_COUNT = 8
COMMAND_REGISTER = 100
SENSOR_FAULT = 0x7FFF
_COMMANDS = {
    CommandKind.UPS_BATTERY_TEST: (1, "Prueba de batería iniciada"),
    CommandKind.UPS_SILENCE_ALARM: (2, "Alarma acústica silenciada"),
}
_REFUSALS = {
    1: "El UPS no admite esa función",
    2: "El UPS no tiene registro de órdenes",
    3: "El UPS no reconoce la orden",
    4: "Falla interna del UPS",
    6: "El UPS está ocupado (hay una prueba en curso): reintentar en unos segundos",
    7: "El UPS no puede ejecutar la orden en su estado actual",
}
_MAX_LOAD_PCT = 150.0
"""A UPS can report overload above 100 %; beyond this the value is not credible."""


def _signed(register: int) -> int:
    return register - 0x10000 if register & 0x8000 else register


def decode(device_id: str, at: datetime, registers: list[int]) -> Reading:
    """Registers to metrics. A value that cannot be right is dropped and the reading becomes PARTIAL:
    shown in yellow, never silently green."""
    problems: list[str] = []
    metrics = {
        "input_voltage_v": registers[3] / 10,
        "output_voltage_v": registers[4] / 10,
        "autonomy_min": float(registers[6]),
        "battery_test": float(bool(registers[7] & 1)),
        "alarm_silenced": float(bool(registers[7] & 2)),
    }
    if (load := registers[0] / 10) <= _MAX_LOAD_PCT:
        metrics["load_pct"] = load
    else:
        problems.append(f"carga imposible ({load:g} %)")
    if (charge := registers[1] / 10) <= 100:  # noqa: PLR2004
        metrics["battery_charge_pct"] = charge
    else:
        problems.append(f"carga de batería imposible ({charge:g} %)")
    if registers[2] == SENSOR_FAULT:
        problems.append("el sensor de temperatura de batería no da valor")
    else:
        metrics["battery_temp_c"] = _signed(registers[2]) / 10
    if registers[5] in (0, 1):
        metrics["on_battery"] = float(registers[5])
    else:
        problems.append(f"estado de batería ilegible ({registers[5]})")
    return assemble(device_id, at, metrics, problems, empty_detail="El UPS no entregó ningún valor válido")


class ModbusUpsDriver:
    def __init__(self, *, timeout_s: float = 3.0, unit: int = 1) -> None:
        self._timeout_s = timeout_s
        self._unit = unit

    async def read(self, device: Device, at: datetime) -> Reading:
        endpoint = device.endpoint
        try:
            registers = await read_input_registers(
                endpoint.host,
                endpoint.port,
                unit=self._unit,
                address=0,
                count=TELEMETRY_COUNT,
                timeout_s=self._timeout_s,
            )
        except Exception as exc:  # every way of failing becomes a classified reading
            failure = classify(exc)
            if failure.cause is FailureCause.UNKNOWN:
                logger.exception("Unclassified failure reading %s", device.id)
            return Reading.failed(device.id, at, failure.cause, failure.detail)
        return decode(device.id, at, registers)

    async def execute(self, device: Device, command: CommandKind) -> str:
        if command not in _COMMANDS:
            raise CommandExecutionError(f"El UPS no acepta la orden {command}")
        code, done = _COMMANDS[command]
        endpoint = device.endpoint
        try:
            await write_register(
                endpoint.host,
                endpoint.port,
                unit=self._unit,
                address=COMMAND_REGISTER,
                value=code,
                timeout_s=self._timeout_s,
            )
        except ModbusExceptionResponse as exc:
            raise CommandExecutionError(_REFUSALS.get(exc.code, f"El UPS rechazó la orden ({exc})")) from exc
        except Exception as exc:
            raise CommandExecutionError(classify(exc).detail) from exc
        return done
