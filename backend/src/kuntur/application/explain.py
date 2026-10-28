"""Explains an alert to the operator: what is happening, why it probably is, what to check first.

The narrator may be a language model, so its answer is treated as untrusted: it can only suggest a
command the device accepts, its texts are capped, and any failure (no credentials, a slow answer, a
refusal, a malformed reply) falls back to the deterministic template. An alert always gets an
explanation, and the screen says which narrator wrote it.
"""

from __future__ import annotations

import asyncio
import logging
from collections import Counter, OrderedDict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from kuntur.application.ports import (
    Clock,
    IncidentContext,
    IncidentNarrator,
    Narration,
    NarratorUnavailable,
    UnitOfWorkFactory,
)
from kuntur.domain.alerts import AlertState
from kuntur.domain.commands import ALLOWED_COMMANDS
from kuntur.domain.errors import NotFoundError

logger = logging.getLogger(__name__)

RECENT_READINGS = 12
HISTORY = timedelta(days=30)
FALLBACK_TTL = timedelta(seconds=60)
"""A template answer given because the narrator failed is retried after this, not kept forever."""
MAX_CAUSES = 4
MAX_CHECKS = 5
MAX_TEXT = 400


@dataclass(frozen=True, slots=True)
class Explanation:
    alert_id: str
    narration: Narration
    generated_at: datetime
    fallback_reason: str | None = None
    """Why the preferred narrator was not used, in words safe to show (details go to the log)."""


def _cut(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1].rstrip() + "…"


def guard(narration: Narration, context: IncidentContext) -> Narration:
    """Whatever the narrator said, the operator only sees short texts and an allowed command."""
    command = narration.suggested_command
    if command is not None and command not in context.allowed_commands:
        logger.warning("Dropped a suggested %s not allowed for %s", command, context.device.id)
        command = None
    return replace(
        narration,
        summary=_cut(narration.summary),
        likely_causes=tuple(_cut(c) for c in narration.likely_causes if c.strip())[:MAX_CAUSES],
        checks=tuple(_cut(c) for c in narration.checks if c.strip())[:MAX_CHECKS],
        suggested_command=command,
    )


class ExplainAlert:
    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        narrator: IncidentNarrator,
        fallback: IncidentNarrator,
        clock: Clock,
        *,
        budget_s: float = 30.0,
        cache_size: int = 256,
    ) -> None:
        self._uow_factory = uow_factory
        self._narrator = narrator
        self._fallback = fallback
        self._clock = clock
        self._budget_s = budget_s
        self._cache_size = cache_size
        self._cache: OrderedDict[tuple[str, AlertState], tuple[Explanation, datetime | None]] = OrderedDict()

    def context(self, alert_id: str) -> IncidentContext:
        now = self._clock.now()
        with self._uow_factory() as uow:
            alert = uow.alerts.get(alert_id)
            if alert is None:
                raise NotFoundError(f"Unknown alert {alert_id}")
            device = uow.devices.get(alert.device_id)
            if device is None:
                raise NotFoundError(f"Unknown device {alert.device_id}")
            readings = uow.readings.recent(device.id, RECENT_READINGS)
            history = uow.alerts.search(state=None, device_id=device.id, limit=500)
            commands = uow.commands.search(device_id=device.id, limit=5)
        previous = sum(
            1 for a in history if a.code is alert.code and a.id != alert.id and a.raised_at >= now - HISTORY
        )
        causes = Counter(r.cause for r in readings if r.cause is not None)
        allowed = tuple(sorted(ALLOWED_COMMANDS[device.kind])) if device.active else ()
        return IncidentContext(
            alert, device, tuple(readings), dict(causes), previous, tuple(commands), allowed, now
        )

    async def _narrate(self, context: IncidentContext) -> tuple[Narration, str | None]:
        try:
            return await asyncio.wait_for(self._narrator.explain(context), self._budget_s), None
        except NarratorUnavailable as exc:
            reason = str(exc) or "no disponible"
        except TimeoutError:
            reason = "tiempo agotado"
        except Exception:
            logger.exception("Narrator crashed explaining alert %s", context.alert.id)
            reason = "error inesperado"
        logger.warning("Explaining alert %s with the template: %s", context.alert.id, reason)
        return await self._fallback.explain(context), reason

    async def __call__(self, alert_id: str) -> Explanation:
        context = await asyncio.to_thread(self.context, alert_id)
        key = (alert_id, context.alert.state)
        cached = self._cache.get(key)
        if cached is not None and (cached[1] is None or cached[1] > context.now):
            self._cache.move_to_end(key)
            return cached[0]
        narration, reason = await self._narrate(context)
        explanation = Explanation(alert_id, guard(narration, context), self._clock.now(), reason)
        self._cache[key] = (explanation, None if reason is None else context.now + FALLBACK_TTL)
        while len(self._cache) > self._cache_size:
            self._cache.popitem(last=False)
        return explanation
