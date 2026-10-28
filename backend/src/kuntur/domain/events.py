"""Domain events: facts that already happened, published after the transaction commits."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from kuntur.domain.alerts import Alert
from kuntur.domain.commands import Command
from kuntur.domain.health import Health
from kuntur.domain.readings import Reading


@dataclass(frozen=True, slots=True)
class DomainEvent:
    occurred_at: datetime


@dataclass(frozen=True, slots=True)
class ReadingRecorded(DomainEvent):
    reading: Reading
    health: Health


@dataclass(frozen=True, slots=True)
class AlertRaised(DomainEvent):
    alert: Alert

    @classmethod
    def of(cls, alert: Alert) -> AlertRaised:
        # Snapshot: later changes to the entity must not rewrite the event
        return cls(alert.raised_at, replace(alert))


@dataclass(frozen=True, slots=True)
class AlertResolved(DomainEvent):
    alert: Alert

    @classmethod
    def of(cls, alert: Alert) -> AlertResolved:
        assert alert.resolved_at is not None  # noqa: S101 - invariant guaranteed by Alert.resolve
        return cls(alert.resolved_at, replace(alert))


@dataclass(frozen=True, slots=True)
class CommandFinished(DomainEvent):
    command: Command

    @classmethod
    def of(cls, command: Command) -> CommandFinished:
        assert command.finished_at is not None  # noqa: S101 - invariant guaranteed by Command._finish
        return cls(command.finished_at, replace(command))
