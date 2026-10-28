"""Minimal Modbus TCP client: functions 4 (read input registers) and 6 (write single register).

Written against the Modbus Application Protocol v1.1b3 and the Modbus Messaging on TCP/IP guide
instead of using pymodbus' client, because that client swallows the connection error and only says
"not connected". A SCADA needs the cause. One connection per request: polling every few seconds does
not need persistent sessions, and a fresh connection shows the network's state as it is now.
"""

from __future__ import annotations

import asyncio
import contextlib
import itertools
import struct

from kuntur.adapters.drivers.failures import ProtocolViolation

_MBAP = struct.Struct(">HHHB")
"""Transaction id, protocol id (always 0), length of what follows, unit id."""
_EXCEPTION_FLAG = 0x80
_READ_INPUT_REGISTERS = 4
_WRITE_SINGLE_REGISTER = 6
_MAX_PDU = 253
_transaction_ids = itertools.count(1)


class ModbusExceptionResponse(Exception):  # noqa: N818 - the protocol's own name
    """The device answered with a Modbus exception (it understood and refused)."""

    def __init__(self, function: int, code: int) -> None:
        super().__init__(f"Excepción Modbus {code} a la función {function}")
        self.function = function
        self.code = code


async def _transact(host: str, port: int, unit: int, pdu: bytes, timeout_s: float) -> bytes:
    transaction = next(_transaction_ids) & 0xFFFF
    async with asyncio.timeout(timeout_s):
        reader, writer = await asyncio.open_connection(host, port)
        try:
            writer.write(_MBAP.pack(transaction, 0, len(pdu) + 1, unit) + pdu)
            await writer.drain()
            answered_transaction, protocol, length, answered_unit = _MBAP.unpack(
                await reader.readexactly(_MBAP.size)
            )
            if protocol != 0 or not 2 <= length <= _MAX_PDU + 1:  # noqa: PLR2004 - function code + data
                raise ProtocolViolation(f"cabecera MBAP inválida (protocolo {protocol}, largo {length})")
            if (answered_transaction, answered_unit) != (transaction, unit):
                raise ProtocolViolation("la respuesta no corresponde a la petición")
            body = await reader.readexactly(length - 1)
        finally:
            writer.close()
            with contextlib.suppress(OSError):
                await writer.wait_closed()
    function = pdu[0]
    if body[0] == function | _EXCEPTION_FLAG:
        raise ModbusExceptionResponse(function, body[1] if len(body) > 1 else 0)
    if body[0] != function:
        raise ProtocolViolation(f"se esperaba la función {function} y llegó la {body[0]}")
    return body


async def read_input_registers(
    host: str, port: int, *, unit: int, address: int, count: int, timeout_s: float
) -> list[int]:
    body = await _transact(
        host, port, unit, struct.pack(">BHH", _READ_INPUT_REGISTERS, address, count), timeout_s
    )
    if len(body) < 2 or body[1] != 2 * count or len(body) != 2 + 2 * count:  # noqa: PLR2004
        raise ProtocolViolation(f"se pidieron {count} registros y llegó otra cantidad")
    return list(struct.unpack(f">{count}H", body[2:]))


async def write_register(
    host: str, port: int, *, unit: int, address: int, value: int, timeout_s: float
) -> None:
    request = struct.pack(">BHH", _WRITE_SINGLE_REGISTER, address, value)
    if await _transact(host, port, unit, request, timeout_s) != request:
        raise ProtocolViolation("el equipo no confirmó la escritura")  # function 6 answers with an echo
