"""What travels over the API. Domain objects are never serialised directly: each one has its own DTO,
so the domain can change without breaking the screens, and nothing leaks by accident."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from kuntur.application.queries import DeviceOverview
from kuntur.domain.alerts import Alert, AlertCode, AlertState, Severity
from kuntur.domain.commands import Command, CommandKind, CommandStatus
from kuntur.domain.devices import Device, DeviceKind
from kuntur.domain.health import Health
from kuntur.domain.lifetime import ClockName, RemainingLife
from kuntur.domain.readings import FailureCause, Reading, ReadingStatus
from kuntur.domain.security import Role


class DeviceOut(BaseModel):
    id: str
    name: str
    kind: DeviceKind
    site: str
    installed_on: date
    active: bool

    @classmethod
    def of(cls, device: Device) -> DeviceOut:
        return cls(
            id=device.id,
            name=device.name,
            kind=device.kind,
            site=device.site,
            installed_on=device.installed_on,
            active=device.active,
        )


class ReadingOut(BaseModel):
    device_id: str
    taken_at: datetime
    status: ReadingStatus
    metrics: dict[str, float]
    cause: FailureCause | None
    detail: str | None

    @classmethod
    def of(cls, reading: Reading) -> ReadingOut:
        return cls(
            device_id=reading.device_id,
            taken_at=reading.taken_at,
            status=reading.status,
            metrics=dict(reading.metrics),
            cause=reading.cause,
            detail=reading.detail,
        )


class AlertOut(BaseModel):
    id: str
    device_id: str
    code: AlertCode
    severity: Severity
    message: str
    raised_at: datetime
    state: AlertState
    resolved_at: datetime | None

    @classmethod
    def of(cls, alert: Alert) -> AlertOut:
        return cls(
            id=alert.id,
            device_id=alert.device_id,
            code=alert.code,
            severity=alert.severity,
            message=alert.message,
            raised_at=alert.raised_at,
            state=alert.state,
            resolved_at=alert.resolved_at,
        )


class LifeClockOut(BaseModel):
    name: ClockName
    consumed_pct: float = Field(description="Porcentaje de vida consumido; puede pasar de 100")
    end_date: date | None = Field(description="Cuándo llega al 100 % al ritmo actual; null si nunca")


class RemainingLifeOut(BaseModel):
    replacement_date: date | None
    governing: ClockName = Field(description="El reloj que se agota primero y marca la fecha")
    overdue: bool
    clocks: list[LifeClockOut]

    @classmethod
    def of(cls, life: RemainingLife, today: date) -> RemainingLifeOut:
        return cls(
            replacement_date=life.replacement_date(today),
            governing=life.governing(today).name,
            overdue=life.overdue(today),
            clocks=[
                LifeClockOut(name=c.name, consumed_pct=round(c.consumed * 100, 2), end_date=c.end_date(today))
                for c in life.clocks
            ],
        )


class DeviceOverviewOut(BaseModel):
    device: DeviceOut
    health: Health
    last_reading: ReadingOut | None
    active_alerts: list[AlertOut]
    life: RemainingLifeOut

    @classmethod
    def of(cls, view: DeviceOverview) -> DeviceOverviewOut:
        return cls(
            device=DeviceOut.of(view.device),
            health=view.health,
            last_reading=ReadingOut.of(view.last_reading) if view.last_reading else None,
            active_alerts=[AlertOut.of(a) for a in view.active_alerts],
            life=RemainingLifeOut.of(view.life, view.today),
        )


class CommandIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: CommandKind


class CommandOut(BaseModel):
    id: str
    device_id: str
    kind: CommandKind
    requested_by: str
    requested_at: datetime
    status: CommandStatus
    finished_at: datetime | None
    detail: str | None

    @classmethod
    def of(cls, command: Command) -> CommandOut:
        return cls(
            id=command.id,
            device_id=command.device_id,
            kind=command.kind,
            requested_by=command.requested_by,
            requested_at=command.requested_at,
            status=command.status,
            finished_at=command.finished_at,
            detail=command.detail,
        )


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=256)


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - the OAuth token type, not a secret
    expires_at: datetime
    username: str
    role: Role


class MeOut(BaseModel):
    username: str
    role: Role
