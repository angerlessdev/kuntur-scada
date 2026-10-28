"""Barrier controller over WebSocket: one JSON request, one JSON answer (see docs/protocolos.md)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from websockets.asyncio.client import connect

from kuntur.adapters.drivers.decoding import assemble
from kuntur.adapters.drivers.failures import ProtocolViolation, classify
from kuntur.application.ports import CommandExecutionError
from kuntur.domain.commands import CommandKind
from kuntur.domain.devices import Device
from kuntur.domain.readings import FailureCause, Reading

logger = logging.getLogger(__name__)

_COUNTERS = ("cycles_total", "impacts_total")
_POSITIONS = {"OPEN": 1.0, "CLOSED": 0.0}
_ACTIONS = {CommandKind.BARRIER_OPEN: "OPEN", CommandKind.BARRIER_CLOSE: "CLOSE"}
_MOTOR_TEMP_RANGE = (-40.0, 150.0)


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def decode(device_id: str, at: datetime, answer: dict[str, Any]) -> Reading:
    if answer.get("op") != "status":
        raise ProtocolViolation(f"se esperaba un estado y llegó {answer.get('op')!r}")
    metrics: dict[str, float] = {}
    problems: list[str] = []
    for name in _COUNTERS:
        value = _number(answer.get(name))
        if value is not None and value >= 0:
            metrics[name] = value
        else:
            problems.append(f"{name} ilegible")
    temperature = _number(answer.get("motor_temp_c"))
    if temperature is not None and _MOTOR_TEMP_RANGE[0] <= temperature <= _MOTOR_TEMP_RANGE[1]:
        metrics["motor_temp_c"] = temperature
    else:
        problems.append("temperatura del motor ilegible")
    if (position := _POSITIONS.get(str(answer.get("position")))) is not None:
        metrics["open"] = position
    else:
        problems.append("posición ilegible")
    if metrics and (fault := answer.get("fault")):
        return Reading.partial(
            device_id, at, metrics, FailureCause.DEVICE_FAULT, f"El controlador reporta falla: {fault}"
        )
    return assemble(
        device_id, at, metrics, problems, empty_detail="El controlador no entregó ningún valor válido"
    )


class WebSocketBarrierDriver:
    def __init__(self, *, timeout_s: float = 3.0) -> None:
        self._timeout_s = timeout_s

    async def _request(self, device: Device, payload: dict[str, str]) -> dict[str, Any]:
        endpoint = device.endpoint
        uri = f"ws://{endpoint.host}:{endpoint.port}{endpoint.path or '/'}"
        async with asyncio.timeout(self._timeout_s):
            async with connect(
                uri, proxy=None, compression=None, open_timeout=None, ping_interval=None, max_size=65_536
            ) as connection:
                await connection.send(json.dumps(payload))
                raw = await connection.recv()
        try:
            answer = json.loads(raw)
        except ValueError as exc:
            raise ProtocolViolation("el controlador no respondió JSON") from exc
        if not isinstance(answer, dict):
            raise ProtocolViolation("el controlador respondió algo que no es un objeto JSON")
        return answer

    async def read(self, device: Device, at: datetime) -> Reading:
        try:
            return decode(device.id, at, await self._request(device, {"op": "status"}))
        except Exception as exc:  # every way of failing becomes a classified reading
            failure = classify(exc)
            if failure.cause is FailureCause.UNKNOWN:
                logger.exception("Unclassified failure reading %s", device.id)
            return Reading.failed(device.id, at, failure.cause, failure.detail)

    async def execute(self, device: Device, command: CommandKind) -> str:
        if command not in _ACTIONS:
            raise CommandExecutionError(f"La barrera no acepta la orden {command}")
        try:
            answer = await self._request(device, {"op": "command", "action": _ACTIONS[command]})
        except Exception as exc:
            raise CommandExecutionError(classify(exc).detail) from exc
        if answer.get("op") != "ack" or not isinstance(answer.get("ok"), bool):
            raise CommandExecutionError("El controlador respondió algo inesperado a la orden")
        detail = str(answer.get("detail") or "")
        if not answer["ok"]:
            raise CommandExecutionError(detail or "El controlador rechazó la orden")
        return detail or "Orden ejecutada"
