"""Device health: the colour an operator sees."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum

from kuntur.domain.alerts import Alert, AlertCode
from kuntur.domain.readings import Reading, ReadingStatus


class Health(StrEnum):
    OK = "OK"
    """Green: the last reading was complete and nothing is active."""
    DEGRADED = "DEGRADED"
    """Yellow: a partial or failed (still unconfirmed) reading, or an active alert."""
    DOWN = "DOWN"
    """Red: loss of contact is confirmed."""
    UNKNOWN = "UNKNOWN"
    """Grey: never read yet."""


def assess_health(last: Reading | None, active_alerts: Iterable[Alert]) -> Health:
    alerts = [alert for alert in active_alerts if alert.is_active]
    if any(alert.code is AlertCode.DEVICE_UNREACHABLE for alert in alerts):
        return Health.DOWN
    if last is None:
        return Health.UNKNOWN
    if last.status is not ReadingStatus.OK or alerts:
        return Health.DEGRADED
    return Health.OK
