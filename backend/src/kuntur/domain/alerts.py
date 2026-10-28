"""Alerts and their lifecycle: ACTIVE -> RESOLVED, nothing else."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from kuntur.domain.errors import DomainValidationError, InvalidTransitionError


class Severity(StrEnum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class AlertState(StrEnum):
    ACTIVE = "ACTIVE"
    RESOLVED = "RESOLVED"


class AlertCode(StrEnum):
    """Every alert the rule engine can raise."""

    DEVICE_UNREACHABLE = "DEVICE_UNREACHABLE"
    UPS_ON_BATTERY = "UPS_ON_BATTERY"
    UPS_BATTERY_LOW = "UPS_BATTERY_LOW"
    UPS_BATTERY_HOT = "UPS_BATTERY_HOT"
    BARRIER_IMPACT = "BARRIER_IMPACT"
    CAMERA_CLOCK_DRIFT = "CAMERA_CLOCK_DRIFT"


@dataclass(slots=True)
class Alert:
    """An alert raised for one device. At most one ACTIVE alert per (device, code)."""

    id: str
    device_id: str
    code: AlertCode
    severity: Severity
    message: str
    raised_at: datetime
    state: AlertState = AlertState.ACTIVE
    resolved_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.raised_at.tzinfo is None:
            raise DomainValidationError("Alert time must be timezone-aware")
        if not self.message.strip():
            raise DomainValidationError("Alert message cannot be empty")
        if (self.state is AlertState.RESOLVED) != (self.resolved_at is not None):
            raise DomainValidationError("Only a resolved alert has a resolution time")

    @property
    def is_active(self) -> bool:
        return self.state is AlertState.ACTIVE

    def resolve(self, at: datetime) -> None:
        if not self.is_active:
            raise InvalidTransitionError(f"Alert {self.id} is already resolved")
        if at < self.raised_at:
            raise InvalidTransitionError("An alert cannot be resolved before it was raised")
        self.state = AlertState.RESOLVED
        self.resolved_at = at

    def duration(self, now: datetime) -> timedelta:
        """How long the alert has been (or was) active."""
        return (self.resolved_at or now) - self.raised_at
