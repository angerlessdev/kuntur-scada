"""IP camera over HTTP with Digest authentication (see docs/protocolos.md).

The clock drift is measured against the middle of the round trip: the device wrote its time somewhere
between our request and its answer, so half the elapsed time is the best estimate of that instant.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from kuntur.adapters.drivers.decoding import assemble
from kuntur.adapters.drivers.failures import AuthenticationFailed, DeviceFault, ProtocolViolation, classify
from kuntur.application.ports import CommandExecutionError
from kuntur.domain.commands import CommandKind
from kuntur.domain.devices import Device
from kuntur.domain.readings import FailureCause, Reading

logger = logging.getLogger(__name__)

_UNAUTHORIZED = 401
_RANGES: dict[str, tuple[float, float, str]] = {
    "storage_free_pct": (0.0, 100.0, "espacio libre ilegible"),
    "temperature_c": (-40.0, 120.0, "temperatura ilegible"),
    "uptime_s": (0.0, float("inf"), "tiempo encendido ilegible"),
}


def _error_detail(response: httpx.Response) -> str:
    try:
        detail = response.json().get("detail")
    except (ValueError, AttributeError):
        detail = None
    return str(detail) if detail else response.reason_phrase


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code == _UNAUTHORIZED:
        raise AuthenticationFailed("La cámara rechazó las credenciales")
    if response.is_server_error:
        raise DeviceFault(f"La cámara no está disponible ({response.status_code}: {_error_detail(response)})")
    if not response.is_success:
        raise ProtocolViolation(f"la cámara respondió {response.status_code}")


def _json_object(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise ProtocolViolation("la cámara no respondió JSON") from exc
    if not isinstance(body, dict):
        raise ProtocolViolation("la cámara respondió algo que no es un objeto JSON")
    return body


def _clock_offset(body: dict[str, Any], reference: datetime) -> float | None:
    """Seconds the device's clock is ahead of ours (negative if behind), or ``None`` if unreadable."""
    try:
        device_time = datetime.fromisoformat(str(body["device_time"]))
    except (KeyError, ValueError):
        return None
    return None if device_time.tzinfo is None else (device_time - reference).total_seconds()


def decode(device_id: str, at: datetime, response: httpx.Response) -> Reading:
    body = _json_object(response)
    metrics: dict[str, float] = {}
    problems: list[str] = []
    offset = _clock_offset(body, at + response.elapsed / 2)
    if offset is None:
        problems.append("hora del equipo ilegible")
    else:
        metrics["clock_offset_s"], metrics["clock_drift_s"] = round(offset, 3), round(abs(offset), 3)
    if isinstance(recording := body.get("recording"), bool):
        metrics["recording"] = float(recording)
    else:
        problems.append("estado de grabación ilegible")
    for name, (low, high, problem) in _RANGES.items():
        value = body.get(name)
        if isinstance(value, int | float) and not isinstance(value, bool) and low <= value <= high:
            metrics[name] = float(value)
        else:
            problems.append(problem)
    return assemble(device_id, at, metrics, problems, empty_detail="La cámara no entregó ningún valor válido")


class HttpCameraDriver:
    """Keeps one HTTP client (and its Digest nonce) for every camera. Close it with ``aclose``."""

    def __init__(self, username: str, password: str, *, timeout_s: float = 3.0) -> None:
        self._client = httpx.AsyncClient(
            auth=httpx.DigestAuth(username, password),
            timeout=timeout_s,
            trust_env=False,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _url(device: Device, action: str) -> str:
        endpoint = device.endpoint
        return f"http://{endpoint.host}:{endpoint.port}{endpoint.path}/{action}"

    async def read(self, device: Device, at: datetime) -> Reading:
        try:
            response = await self._client.get(self._url(device, "status"))
            _raise_for_status(response)
            return decode(device.id, at, response)
        except Exception as exc:  # every way of failing becomes a classified reading
            failure = classify(exc)
            if failure.cause is FailureCause.UNKNOWN:
                logger.exception("Unclassified failure reading %s", device.id)
            return Reading.failed(device.id, at, failure.cause, failure.detail)

    async def execute(self, device: Device, command: CommandKind) -> str:
        if command is not CommandKind.CAMERA_REBOOT:
            raise CommandExecutionError(f"La cámara no acepta la orden {command}")
        try:
            response = await self._client.post(self._url(device, "reboot"))
        except Exception as exc:
            raise CommandExecutionError(classify(exc).detail) from exc
        if response.status_code == _UNAUTHORIZED:
            raise CommandExecutionError("La cámara rechazó las credenciales")
        if not response.is_success:
            raise CommandExecutionError(_error_detail(response))
        return _error_detail(response) if response.content else "Reinicio en curso"
