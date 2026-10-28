"""Live updates over WebSocket.

A browser cannot set headers on a WebSocket, and a token in the URL ends up in access logs, so the
session token travels as the first message, ``{"token": "..."}``, within ``AUTH_TIMEOUT_S``. The
channel is read-only: commands go through the HTTP API, where they are audited.
"""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool

from kuntur.bootstrap import Application
from kuntur.domain.errors import AuthenticationError

router = APIRouter()

AUTH_TIMEOUT_S = 5.0
UNAUTHENTICATED = 4401
"""Close code for a channel opened without a valid session (4000-4999 are free for applications)."""


@router.websocket("/api/v1/live")
async def live(websocket: WebSocket) -> None:
    application: Application = websocket.app.state.application
    await websocket.accept()
    try:
        first = await asyncio.wait_for(websocket.receive_json(), AUTH_TIMEOUT_S)
        token = first.get("token") if isinstance(first, dict) else None
        if not isinstance(token, str):
            raise AuthenticationError("Falta el token de sesión")
        actor = await run_in_threadpool(application.resolve_actor, token)
    except WebSocketDisconnect:
        return
    except (TimeoutError, ValueError, KeyError, AuthenticationError):
        await websocket.close(code=UNAUTHENTICATED, reason="Autenticación requerida")
        return

    await websocket.send_json({"type": "hello", "username": actor.username, "role": actor.role.value})
    with application.hub.subscribe() as queue:

        async def forward() -> None:
            while True:
                await websocket.send_text(await queue.get())

        sender = asyncio.create_task(forward(), name=f"live-{actor.username}")
        try:
            while True:
                await websocket.receive_text()  # screens do not talk; this only notices they left
        except WebSocketDisconnect:
            pass
        finally:
            sender.cancel()
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                await sender
