"""Turns whatever went wrong talking to a device into one cause of the closed taxonomy, with a message
an operator can act on. Every driver uses it, so the same failure reads the same on every screen."""

from __future__ import annotations

import asyncio
import errno
import socket
from collections.abc import Iterator
from dataclasses import dataclass

import httpx
import websockets.exceptions as ws

from kuntur.domain.readings import FailureCause


class ProtocolViolation(Exception):  # noqa: N818 - named after what the device did
    """Something answered, but not in the expected protocol. The message says what was wrong."""


class AuthenticationFailed(Exception):  # noqa: N818
    """The device rejected the credentials."""


class DeviceFault(Exception):  # noqa: N818
    """The device answered that it cannot serve the request (internal fault, rebooting...)."""


@dataclass(frozen=True, slots=True)
class Failure:
    cause: FailureCause
    detail: str


_UNREACHABLE_ERRNOS = frozenset(
    code
    for name in (
        "ENETUNREACH",
        "EHOSTUNREACH",
        "EHOSTDOWN",
        "WSAENETUNREACH",
        "WSAEHOSTUNREACH",
        "WSAEHOSTDOWN",
    )
    if (code := getattr(errno, name, None)) is not None
)


def _chain(exc: BaseException) -> Iterator[BaseException]:
    """The exception and the ones it wraps: httpx and websockets wrap the operating system's error."""
    seen: set[int] = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        yield current
        current = current.__cause__ or current.__context__


def _direct(exc: BaseException) -> Failure | None:  # noqa: PLR0911 - one return per cause reads best
    match exc:
        case TimeoutError() | httpx.TimeoutException():
            return Failure(FailureCause.TIMEOUT, "El equipo no respondió a tiempo")
        case ConnectionRefusedError():
            return Failure(
                FailureCause.CONNECTION_REFUSED, "Conexión rechazada: el equipo no atiende en ese puerto"
            )
        case socket.gaierror():
            return Failure(FailureCause.UNREACHABLE, "No se pudo resolver la dirección del equipo")
        case (
            ConnectionResetError()
            | ConnectionAbortedError()
            | BrokenPipeError()
            | asyncio.IncompleteReadError()
            | ws.ConnectionClosed()
            | httpx.RemoteProtocolError()
        ):
            return Failure(FailureCause.CONNECTION_LOST, "La conexión se cortó antes de la respuesta")
        case OSError() if exc.errno in _UNREACHABLE_ERRNOS:
            return Failure(FailureCause.UNREACHABLE, "Sin ruta hacia el equipo")
        case AuthenticationFailed():
            return Failure(FailureCause.AUTH_FAILED, str(exc) or "El equipo rechazó las credenciales")
        case ProtocolViolation():
            return Failure(FailureCause.PROTOCOL_ERROR, f"Respuesta fuera de protocolo: {exc}")
        case ws.InvalidHandshake() | ws.InvalidURI() | httpx.DecodingError():
            return Failure(
                FailureCause.PROTOCOL_ERROR, f"Respuesta fuera de protocolo ({type(exc).__name__})"
            )
        case DeviceFault():
            return Failure(FailureCause.DEVICE_FAULT, str(exc))
        case _:
            return None


def classify(exc: BaseException) -> Failure:
    for link in _chain(exc):
        failure = _direct(link)
        if failure is not None:
            return failure
    if isinstance(exc, httpx.ConnectError):  # a connect failure whose system error was not kept
        return Failure(FailureCause.UNREACHABLE, "No se pudo conectar con el equipo")
    return Failure(FailureCause.UNKNOWN, f"Error no clasificado ({type(exc).__name__})")
