"""Supervisory control: the 'control' in SCADA. Every command is audited."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from types import MappingProxyType

from kuntur.domain.devices import Device, DeviceKind
from kuntur.domain.errors import CommandNotAllowedError, DomainValidationError, InvalidTransitionError


class CommandKind(StrEnum):
    UPS_BATTERY_TEST = "UPS_BATTERY_TEST"
    UPS_SILENCE_ALARM = "UPS_SILENCE_ALARM"
    BARRIER_OPEN = "BARRIER_OPEN"
    BARRIER_CLOSE = "BARRIER_CLOSE"
    CAMERA_REBOOT = "CAMERA_REBOOT"


ALLOWED_COMMANDS: Mapping[DeviceKind, frozenset[CommandKind]] = MappingProxyType(
    {
        DeviceKind.UPS: frozenset({CommandKind.UPS_BATTERY_TEST, CommandKind.UPS_SILENCE_ALARM}),
        DeviceKind.BARRIER: frozenset({CommandKind.BARRIER_OPEN, CommandKind.BARRIER_CLOSE}),
        DeviceKind.CAMERA: frozenset({CommandKind.CAMERA_REBOOT}),
    }
)


EXPECTED_DOWNTIME: Mapping[CommandKind, timedelta] = MappingProxyType(
    {CommandKind.CAMERA_REBOOT: timedelta(seconds=90)}
)
"""How long a successful command takes the device off the network. A camera needs about a minute to
boot; until then its silence is expected, not an alarm."""


class CommandStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


@dataclass(slots=True)
class Command:
    """A command sent to a device, with who asked for it and how it ended."""

    id: str
    device_id: str
    kind: CommandKind
    requested_by: str
    requested_at: datetime
    status: CommandStatus = CommandStatus.PENDING
    finished_at: datetime | None = None
    detail: str | None = None

    def __post_init__(self) -> None:
        if self.requested_at.tzinfo is None:
            raise DomainValidationError("Command time must be timezone-aware")
        if not self.requested_by.strip():
            raise DomainValidationError("Every command needs an author")

    def succeed(self, at: datetime, detail: str | None = None) -> None:
        self._finish(CommandStatus.SUCCEEDED, at, detail)

    def expected_down_until(self) -> datetime | None:
        """Until when the device is down on purpose because of this command, if it is."""
        downtime = EXPECTED_DOWNTIME.get(self.kind)
        if downtime is None or self.status is not CommandStatus.SUCCEEDED or self.finished_at is None:
            return None
        return self.finished_at + downtime

    def fail(self, at: datetime, detail: str) -> None:
        self._finish(CommandStatus.FAILED, at, detail)

    def _finish(self, status: CommandStatus, at: datetime, detail: str | None) -> None:
        if self.status is not CommandStatus.PENDING:
            raise InvalidTransitionError(f"Command {self.id} already finished as {self.status}")
        if at < self.requested_at:
            raise InvalidTransitionError("A command cannot finish before it was requested")
        self.status, self.finished_at, self.detail = status, at, detail


def ensure_command_allowed(device: Device, kind: CommandKind) -> None:
    if not device.active:
        raise CommandNotAllowedError(f"Device {device.id} is out of service")
    if kind not in ALLOWED_COMMANDS[device.kind]:
        raise CommandNotAllowedError(f"{kind} is not a command for a {device.kind}")
