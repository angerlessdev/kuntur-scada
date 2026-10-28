"""Barrier controller over WebSocket: JSON requests, one answer per request.

Requests and answers::

    {"op": "status"}                       -> {"op": "status", "position": "CLOSED", "cycles_total": 1650000,
                                               "impacts_total": 41, "motor_temp_c": 35.2, "fault": null}
    {"op": "command", "action": "OPEN"}    -> {"op": "ack", "ok": true, "detail": "Barrera abierta"}
    anything else                          -> {"op": "error", "detail": "..."}
"""

from __future__ import annotations

import json
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, serve

from kuntur_sim.models import BarrierModel, CommandRejected


class BarrierWebSocketServer:
    def __init__(self, model: BarrierModel, host: str = "127.0.0.1", port: int = 0) -> None:
        self._model = model
        self._host = host
        self._port = port
        self._server: Server | None = None

    async def start(self) -> int:
        self._server = await serve(self._handle, self._host, self._port, compression=None)
        return int(next(iter(self._server.sockets)).getsockname()[1])

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, connection: ServerConnection) -> None:
        async for message in connection:
            await connection.send(json.dumps(self.answer(message), ensure_ascii=False))

    def answer(self, message: str | bytes) -> dict[str, Any]:
        try:
            request = json.loads(message)
            op = request["op"]
        except (ValueError, KeyError, TypeError):
            return {"op": "error", "detail": "Mensaje inválido"}
        if op == "status":
            model = self._model
            return {
                "op": "status",
                "position": model.position,
                "cycles_total": model.cycles_total,
                "impacts_total": model.impacts_total,
                "motor_temp_c": round(model.motor_temp_c, 1),
                "fault": "MOTOR" if model.faulted else None,
            }
        if op == "command":
            actions = {"OPEN": self._model.open, "CLOSE": self._model.close}
            action = actions.get(str(request.get("action")))
            if action is None:
                return {"op": "ack", "ok": False, "detail": f"Acción desconocida: {request.get('action')}"}
            try:
                return {"op": "ack", "ok": True, "detail": action()}
            except CommandRejected as exc:
                return {"op": "ack", "ok": False, "detail": str(exc)}
        return {"op": "error", "detail": f"Operación desconocida: {op}"}
