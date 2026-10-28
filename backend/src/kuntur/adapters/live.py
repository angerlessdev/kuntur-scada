"""Fans domain events out to the screens connected over WebSocket.

Events arrive from worker threads (readings are recorded off the event loop); they are handed to the
loop thread-safely. Each screen has its own bounded queue: a slow one loses its oldest messages
instead of slowing everyone else down.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Iterator
from typing import Any

from kuntur.domain.events import AlertRaised, AlertResolved, CommandFinished, DomainEvent, ReadingRecorded

logger = logging.getLogger(__name__)


def encode(event: DomainEvent) -> str | None:
    # The DTOs live with the API; imported here lazily to keep this module free of FastAPI at import
    from kuntur.adapters.api.schemas import AlertOut, CommandOut, ReadingOut  # noqa: PLC0415

    payload: dict[str, Any]
    match event:
        case ReadingRecorded(reading=reading, health=health, kind=kind):
            payload = {
                "type": "reading",
                "device_id": reading.device_id,
                "kind": kind,
                "health": health,
                "reading": ReadingOut.of(reading).model_dump(mode="json"),
            }
        case AlertRaised(alert=alert):
            payload = {"type": "alert_raised", "alert": AlertOut.of(alert).model_dump(mode="json")}
        case AlertResolved(alert=alert):
            payload = {"type": "alert_resolved", "alert": AlertOut.of(alert).model_dump(mode="json")}
        case CommandFinished(command=command):
            payload = {"type": "command_finished", "command": CommandOut.of(command).model_dump(mode="json")}
        case _:
            return None
    return json.dumps(payload, ensure_ascii=False)


class LiveHub:
    def __init__(self, queue_size: int = 256) -> None:
        self._queue_size = queue_size
        self._clients: set[asyncio.Queue[str]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def clients(self) -> int:
        return len(self._clients)

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def unbind(self) -> None:
        self._loop = None

    def handle(self, event: DomainEvent) -> None:
        """Event bus subscriber: safe to call from any thread."""
        loop = self._loop
        if loop is None or not self._clients:
            return
        message = encode(event)
        if message is None:
            return
        with contextlib.suppress(RuntimeError):  # the loop is shutting down
            loop.call_soon_threadsafe(self._broadcast, message)

    def _broadcast(self, message: str) -> None:
        for queue in list(self._clients):
            if queue.full():
                queue.get_nowait()  # drop the oldest: this screen is not keeping up
            queue.put_nowait(message)

    @contextlib.contextmanager
    def subscribe(self) -> Iterator[asyncio.Queue[str]]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self._queue_size)
        self._clients.add(queue)
        try:
            yield queue
        finally:
            self._clients.discard(queue)
