"""Readings: one acquisition attempt against a device, successful or not."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

from kuntur.domain.errors import DomainValidationError


class ReadingStatus(StrEnum):
    """``PARTIAL`` means the device answered but part of the data is missing or wrong.

    A partial read is never shown as healthy: it is the difference between a quiet
    green screen and an honest yellow one.
    """

    OK = "OK"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"


class FailureCause(StrEnum):
    """Why an acquisition failed. One closed taxonomy shared by every protocol driver."""

    TIMEOUT = "TIMEOUT"
    """The device did not answer in time."""
    CONNECTION_REFUSED = "CONNECTION_REFUSED"
    """The host is up but nothing listens on the port."""
    UNREACHABLE = "UNREACHABLE"
    """No route to the host: network down, wrong address or name resolution failure."""
    CONNECTION_LOST = "CONNECTION_LOST"
    """The connection opened but dropped before the answer: a flapping link, a device rebooting."""
    AUTH_FAILED = "AUTH_FAILED"
    """The device rejected the credentials."""
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    """Something answered, but not in the expected protocol."""
    INVALID_DATA = "INVALID_DATA"
    """The protocol worked but the values are malformed or out of range."""
    DEVICE_FAULT = "DEVICE_FAULT"
    """The device itself reports an internal fault."""
    UNKNOWN = "UNKNOWN"
    """Anything the driver could not classify."""


CAUSE_LABELS: Mapping[FailureCause, str] = MappingProxyType(
    {
        FailureCause.TIMEOUT: "no respondió a tiempo",
        FailureCause.CONNECTION_REFUSED: "conexión rechazada",
        FailureCause.UNREACHABLE: "sin ruta de red",
        FailureCause.CONNECTION_LOST: "conexión cortada",
        FailureCause.AUTH_FAILED: "credenciales rechazadas",
        FailureCause.PROTOCOL_ERROR: "respuesta fuera de protocolo",
        FailureCause.INVALID_DATA: "valores imposibles",
        FailureCause.DEVICE_FAULT: "falla del equipo",
        FailureCause.UNKNOWN: "falla sin clasificar",
    }
)
"""How each cause reads in an operator-facing message."""


@dataclass(frozen=True, slots=True)
class Reading:
    """Immutable result of polling a device once. ``taken_at`` must be timezone-aware."""

    device_id: str
    taken_at: datetime
    status: ReadingStatus
    metrics: Mapping[str, float] = field(default_factory=dict)
    cause: FailureCause | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.taken_at.tzinfo is None:
            raise DomainValidationError("Reading time must be timezone-aware")
        if self.status is ReadingStatus.OK and self.cause is not None:
            raise DomainValidationError("A successful reading cannot carry a failure cause")
        if self.status is not ReadingStatus.OK and self.cause is None:
            raise DomainValidationError(f"A {self.status} reading needs a failure cause")
        if self.status is ReadingStatus.FAILED and self.metrics:
            raise DomainValidationError("A failed reading cannot carry metrics")
        if self.status is ReadingStatus.PARTIAL and not self.metrics:
            raise DomainValidationError("A partial reading must carry the metrics that did arrive")
        # Freeze the mapping so a reading cannot be altered after it is recorded
        object.__setattr__(self, "metrics", MappingProxyType(dict(self.metrics)))

    @classmethod
    def ok(cls, device_id: str, taken_at: datetime, metrics: Mapping[str, float]) -> Reading:
        return cls(device_id, taken_at, ReadingStatus.OK, metrics)

    @classmethod
    def partial(
        cls,
        device_id: str,
        taken_at: datetime,
        metrics: Mapping[str, float],
        cause: FailureCause,
        detail: str | None = None,
    ) -> Reading:
        return cls(device_id, taken_at, ReadingStatus.PARTIAL, metrics, cause, detail)

    @classmethod
    def failed(
        cls, device_id: str, taken_at: datetime, cause: FailureCause, detail: str | None = None
    ) -> Reading:
        return cls(device_id, taken_at, ReadingStatus.FAILED, {}, cause, detail)

    @property
    def answered(self) -> bool:
        """True when the device answered at all (OK or PARTIAL)."""
        return self.status is not ReadingStatus.FAILED

    def metric(self, name: str) -> float | None:
        return self.metrics.get(name)
