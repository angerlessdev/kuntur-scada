"""In-process event bus: the use cases publish, the WebSocket hub and the metrics listen."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable, Sequence

from kuntur.domain.events import DomainEvent

logger = logging.getLogger(__name__)

Handler = Callable[[DomainEvent], None]


class InMemoryEventBus:
    def __init__(self) -> None:
        self._handlers: list[Handler] = []
        self._lock = threading.Lock()

    def subscribe(self, handler: Handler) -> Callable[[], None]:
        with self._lock:
            self._handlers.append(handler)

        def unsubscribe() -> None:
            with self._lock:
                if handler in self._handlers:
                    self._handlers.remove(handler)

        return unsubscribe

    def publish(self, events: Sequence[DomainEvent]) -> None:
        with self._lock:
            handlers = list(self._handlers)
        for event in events:
            for handler in handlers:
                try:
                    handler(event)
                except Exception:  # one broken listener must not silence the others
                    logger.exception("Event handler failed for %s", type(event).__name__)
