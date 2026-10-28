"""Ports: what the application needs from the outside world, expressed as protocols.

Adapters implement them (SQL Server, Modbus, HTTP, an LLM...). The use cases only see these
interfaces, so every dependency points inwards and any adapter can be swapped or faked in tests.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self

from kuntur.domain.alerts import Alert, AlertCode, AlertState
from kuntur.domain.commands import Command, CommandKind
from kuntur.domain.devices import Device, DeviceKind
from kuntur.domain.events import DomainEvent
from kuntur.domain.readings import Reading
from kuntur.domain.security import Actor, User


class DeviceRepository(Protocol):
    def get(self, device_id: str) -> Device | None: ...

    def list(self, *, active_only: bool = False) -> list[Device]: ...

    def add(self, device: Device) -> None: ...

    def update(self, device: Device) -> None: ...


class ReadingRepository(Protocol):
    def add(self, reading: Reading) -> None: ...

    def recent(self, device_id: str, limit: int) -> list[Reading]:
        """The newest ``limit`` readings, ordered oldest first."""
        ...

    def latest(self, device_id: str, *, answered_only: bool = False) -> Reading | None: ...

    def history(self, device_id: str, since: datetime, limit: int) -> list[Reading]:
        """Readings taken at or after ``since``, oldest first, at most ``limit``."""
        ...

    def average(self, device_id: str, metric: str, since: datetime) -> float | None: ...


class AlertRepository(Protocol):
    def add(self, alert: Alert) -> None: ...

    def update(self, alert: Alert) -> None: ...

    def get(self, alert_id: str) -> Alert | None: ...

    def active(self, device_id: str | None = None) -> list[Alert]: ...

    def last_resolved_at(self, device_id: str) -> dict[AlertCode, datetime]: ...

    def search(self, *, state: AlertState | None, device_id: str | None, limit: int) -> list[Alert]:
        """Newest first."""
        ...


class CommandRepository(Protocol):
    def add(self, command: Command) -> None: ...

    def update(self, command: Command) -> None: ...

    def search(self, *, device_id: str | None, limit: int) -> list[Command]:
        """Newest first: this is the audit log."""
        ...


class UserRepository(Protocol):
    def get(self, username: str) -> User | None: ...

    def add(self, user: User) -> None: ...

    def update(self, user: User) -> None: ...


class UnitOfWork(Protocol):
    """One business transaction. Leaving the block without ``commit()`` rolls everything back."""

    devices: DeviceRepository
    readings: ReadingRepository
    alerts: AlertRepository
    commands: CommandRepository
    users: UserRepository

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]


class EventPublisher(Protocol):
    def publish(self, events: Sequence[DomainEvent]) -> None: ...


class Clock(Protocol):
    def now(self) -> datetime:
        """Current time, timezone-aware (UTC)."""
        ...


class IdGenerator(Protocol):
    def new_id(self) -> str: ...


class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...


@dataclass(frozen=True, slots=True)
class IssuedToken:
    token: str
    expires_at: datetime
    actor: Actor


class TokenService(Protocol):
    def issue(self, actor: Actor) -> IssuedToken: ...

    def subject(self, token: str) -> str:
        """The username the token was issued to. Raises ``AuthenticationError`` if it is not valid."""
        ...


class CommandExecutionError(Exception):
    """The device refused or could not carry out a command. The message is shown to the operator."""


class DeviceDriver(Protocol):
    """Speaks one device protocol. ``read`` never raises for device problems: it returns a FAILED or
    PARTIAL reading with a classified cause. ``execute`` raises ``CommandExecutionError``."""

    async def read(self, device: Device, at: datetime) -> Reading: ...

    async def execute(self, device: Device, command: CommandKind) -> str: ...


class DriverRegistry(Protocol):
    def for_kind(self, kind: DeviceKind) -> DeviceDriver: ...
