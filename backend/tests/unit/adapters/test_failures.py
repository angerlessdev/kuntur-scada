import asyncio
import errno
import socket

import httpx
import pytest
import websockets.exceptions as ws

from kuntur.adapters.drivers.failures import AuthenticationFailed, DeviceFault, ProtocolViolation, classify
from kuntur.domain.readings import FailureCause


def _wrapped(outer: Exception, inner: BaseException) -> Exception:
    """``outer`` raised from ``inner``, the way httpx wraps the operating system's error."""
    try:
        try:
            raise inner
        except BaseException as exc:
            raise outer from exc
    except Exception as exc:
        return exc
    raise AssertionError("unreachable")


@pytest.mark.parametrize(
    ("exc", "cause"),
    [
        (TimeoutError(), FailureCause.TIMEOUT),
        (httpx.ReadTimeout("lento"), FailureCause.TIMEOUT),
        (ConnectionRefusedError(), FailureCause.CONNECTION_REFUSED),
        (socket.gaierror(socket.EAI_NONAME, "sin nombre"), FailureCause.UNREACHABLE),
        (OSError(errno.EHOSTUNREACH, "sin ruta"), FailureCause.UNREACHABLE),
        (ConnectionResetError(), FailureCause.CONNECTION_LOST),
        (asyncio.IncompleteReadError(b"", 7), FailureCause.CONNECTION_LOST),
        (ws.ConnectionClosedError(None, None), FailureCause.CONNECTION_LOST),
        (httpx.RemoteProtocolError("Server disconnected"), FailureCause.CONNECTION_LOST),
        (AuthenticationFailed("La cámara rechazó las credenciales"), FailureCause.AUTH_FAILED),
        (ProtocolViolation("cabecera MBAP inválida"), FailureCause.PROTOCOL_ERROR),
        (ws.InvalidURI("ws//x", "falta el esquema"), FailureCause.PROTOCOL_ERROR),
        (DeviceFault("Reiniciando"), FailureCause.DEVICE_FAULT),
        (httpx.ConnectError("All connection attempts failed"), FailureCause.UNREACHABLE),
        (ValueError("bug"), FailureCause.UNKNOWN),
    ],
    ids=lambda value: type(value).__name__ if isinstance(value, BaseException) else str(value),
)
def test_every_failure_has_exactly_one_cause(exc: BaseException, cause: FailureCause) -> None:
    assert classify(exc).cause is cause


def test_the_cause_is_found_inside_a_library_wrapper() -> None:
    wrapped = _wrapped(httpx.ConnectError("All connection attempts failed"), ConnectionRefusedError())
    assert classify(wrapped).cause is FailureCause.CONNECTION_REFUSED


def test_the_operator_reads_what_to_check() -> None:
    assert (
        classify(ConnectionRefusedError()).detail == "Conexión rechazada: el equipo no atiende en ese puerto"
    )
    assert classify(ProtocolViolation("la respuesta no corresponde a la petición")).detail == (
        "Respuesta fuera de protocolo: la respuesta no corresponde a la petición"
    )
    assert classify(KeyError("x")).detail == "Error no clasificado (KeyError)"
