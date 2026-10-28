"""Repositories over one SQLAlchemy connection. Rows and entities are mapped explicitly, in both ways."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Connection, RowMapping, Select, and_, func, insert, select, true, update
from sqlalchemy.exc import IntegrityError

from kuntur.adapters.persistence.sql.schema import TEXT_LIMIT, alerts, commands, devices, readings, users
from kuntur.domain.alerts import Alert, AlertCode, AlertState, Severity
from kuntur.domain.commands import Command, CommandKind, CommandStatus
from kuntur.domain.devices import Device, DeviceKind, Endpoint, LifetimeProfile
from kuntur.domain.readings import FailureCause, Reading, ReadingStatus
from kuntur.domain.security import Role, User

Row = RowMapping


def _cut(text: str | None) -> str | None:
    return None if text is None else text[:TEXT_LIMIT]


def _device_values(device: Device) -> dict[str, Any]:
    return {
        "id": device.id,
        "name": device.name,
        "kind": device.kind.value,
        "site": device.site,
        "host": device.endpoint.host,
        "port": device.endpoint.port,
        "path": device.endpoint.path,
        "installed_on": device.installed_on,
        "design_life_years": device.lifetime.design_life_years,
        "rated_cycles": device.lifetime.rated_cycles,
        "rated_impacts": device.lifetime.rated_impacts,
        "battery_design_life_years": device.lifetime.battery_design_life_years,
        "active": device.active,
    }


def _device(row: Row) -> Device:
    return Device(
        row["id"],
        row["name"],
        DeviceKind(row["kind"]),
        row["site"],
        Endpoint(row["host"], row["port"], row["path"]),
        row["installed_on"],
        LifetimeProfile(
            row["design_life_years"],
            row["rated_cycles"],
            row["rated_impacts"],
            row["battery_design_life_years"],
        ),
        bool(row["active"]),
    )


def _reading(row: Row) -> Reading:
    return Reading(
        row["device_id"],
        row["taken_at"],
        ReadingStatus(row["status"]),
        row["metrics"],
        FailureCause(row["cause"]) if row["cause"] else None,
        row["detail"],
    )


def _alert_values(alert: Alert) -> dict[str, Any]:
    return {
        "id": alert.id,
        "device_id": alert.device_id,
        "code": alert.code.value,
        "severity": alert.severity.value,
        "message": _cut(alert.message),
        "raised_at": alert.raised_at,
        "state": alert.state.value,
        "resolved_at": alert.resolved_at,
    }


def _alert(row: Row) -> Alert:
    return Alert(
        row["id"],
        row["device_id"],
        AlertCode(row["code"]),
        Severity(row["severity"]),
        row["message"],
        row["raised_at"],
        AlertState(row["state"]),
        row["resolved_at"],
    )


def _command_values(command: Command) -> dict[str, Any]:
    return {
        "id": command.id,
        "device_id": command.device_id,
        "kind": command.kind.value,
        "requested_by": command.requested_by,
        "requested_at": command.requested_at,
        "status": command.status.value,
        "finished_at": command.finished_at,
        "detail": _cut(command.detail),
    }


def _command(row: Row) -> Command:
    return Command(
        row["id"],
        row["device_id"],
        CommandKind(row["kind"]),
        row["requested_by"],
        row["requested_at"],
        CommandStatus(row["status"]),
        row["finished_at"],
        row["detail"],
    )


class SqlDeviceRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, device_id: str) -> Device | None:
        row = self._connection.execute(select(devices).where(devices.c.id == device_id)).mappings().first()
        return _device(row) if row is not None else None

    def list(self, *, active_only: bool = False) -> list[Device]:
        query = select(devices).order_by(devices.c.id)
        if active_only:
            query = query.where(devices.c.active == true())
        return [_device(row) for row in self._connection.execute(query).mappings()]

    def add(self, device: Device) -> None:
        try:
            with self._connection.begin_nested():
                self._connection.execute(insert(devices).values(_device_values(device)))
        except IntegrityError as exc:
            raise ValueError(f"Device {device.id} already exists") from exc

    def update(self, device: Device) -> None:
        values = _device_values(device)
        del values["id"]
        result = self._connection.execute(update(devices).where(devices.c.id == device.id).values(values))
        if result.rowcount == 0:
            raise KeyError(device.id)


class SqlReadingRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def _query(self, query: Select[Any]) -> list[Reading]:
        return [_reading(row) for row in self._connection.execute(query).mappings()]

    def add(self, reading: Reading) -> None:
        values = {
            "device_id": reading.device_id,
            "taken_at": reading.taken_at,
            "status": reading.status.value,
            "cause": reading.cause.value if reading.cause else None,
            "detail": _cut(reading.detail),
            "metrics": dict(reading.metrics),
        }
        self._connection.execute(insert(readings).values(values))

    def recent(self, device_id: str, limit: int) -> list[Reading]:
        if limit <= 0:
            return []
        query = (
            select(readings)
            .where(readings.c.device_id == device_id)
            .order_by(readings.c.taken_at.desc(), readings.c.id.desc())
            .limit(limit)
        )
        return list(reversed(self._query(query)))

    def latest(self, device_id: str, *, answered_only: bool = False) -> Reading | None:
        query = (
            select(readings)
            .where(readings.c.device_id == device_id)
            .order_by(readings.c.taken_at.desc(), readings.c.id.desc())
            .limit(1)
        )
        if answered_only:
            query = query.where(readings.c.status != ReadingStatus.FAILED.value)
        found = self._query(query)
        return found[0] if found else None

    def history(self, device_id: str, since: datetime, limit: int) -> list[Reading]:
        query = (
            select(readings)
            .where(and_(readings.c.device_id == device_id, readings.c.taken_at >= since))
            .order_by(readings.c.taken_at, readings.c.id)
            .limit(limit)
        )
        return self._query(query)

    def average(self, device_id: str, metric: str, since: datetime) -> float | None:
        # AVG skips the NULLs that JSON_VALUE gives readings without the metric, like the domain expects
        query = select(func.avg(readings.c.metrics[metric].as_float())).where(
            and_(readings.c.device_id == device_id, readings.c.taken_at >= since)
        )
        value = self._connection.execute(query).scalar()
        return None if value is None else float(value)


class SqlAlertRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add(self, alert: Alert) -> None:
        self._connection.execute(insert(alerts).values(_alert_values(alert)))

    def update(self, alert: Alert) -> None:
        values = _alert_values(alert)
        del values["id"]
        result = self._connection.execute(update(alerts).where(alerts.c.id == alert.id).values(values))
        if result.rowcount == 0:
            raise KeyError(alert.id)

    def get(self, alert_id: str) -> Alert | None:
        row = self._connection.execute(select(alerts).where(alerts.c.id == alert_id)).mappings().first()
        return _alert(row) if row is not None else None

    def active(self, device_id: str | None = None) -> list[Alert]:
        query = select(alerts).where(alerts.c.state == AlertState.ACTIVE.value)
        if device_id is not None:
            query = query.where(alerts.c.device_id == device_id)
        query = query.order_by(alerts.c.raised_at, alerts.c.id)
        return [_alert(row) for row in self._connection.execute(query).mappings()]

    def last_resolved_at(self, device_id: str) -> dict[AlertCode, datetime]:
        query = (
            select(alerts.c.code, func.max(alerts.c.resolved_at).label("resolved_at"))
            .where(and_(alerts.c.device_id == device_id, alerts.c.resolved_at.is_not(None)))
            .group_by(alerts.c.code)
        )
        return {
            AlertCode(row["code"]): row["resolved_at"] for row in self._connection.execute(query).mappings()
        }

    def search(self, *, state: AlertState | None, device_id: str | None, limit: int) -> list[Alert]:
        query = select(alerts).order_by(alerts.c.raised_at.desc(), alerts.c.id.desc()).limit(limit)
        if state is not None:
            query = query.where(alerts.c.state == state.value)
        if device_id is not None:
            query = query.where(alerts.c.device_id == device_id)
        return [_alert(row) for row in self._connection.execute(query).mappings()]


class SqlCommandRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def add(self, command: Command) -> None:
        self._connection.execute(insert(commands).values(_command_values(command)))

    def update(self, command: Command) -> None:
        values = _command_values(command)
        del values["id"]
        result = self._connection.execute(update(commands).where(commands.c.id == command.id).values(values))
        if result.rowcount == 0:
            raise KeyError(command.id)

    def search(self, *, device_id: str | None, limit: int) -> list[Command]:
        query = select(commands).order_by(commands.c.requested_at.desc(), commands.c.id.desc()).limit(limit)
        if device_id is not None:
            query = query.where(commands.c.device_id == device_id)
        return [_command(row) for row in self._connection.execute(query).mappings()]


class SqlUserRepository:
    def __init__(self, connection: Connection) -> None:
        self._connection = connection

    def get(self, username: str) -> User | None:
        row = self._connection.execute(select(users).where(users.c.username == username)).mappings().first()
        if row is None:
            return None
        return User(row["username"], row["password_hash"], Role(row["role"]), bool(row["active"]))

    def add(self, user: User) -> None:
        values = {"username": user.username, "password_hash": user.password_hash, "role": user.role.value}
        try:
            with self._connection.begin_nested():
                self._connection.execute(insert(users).values({**values, "active": user.active}))
        except IntegrityError as exc:
            raise ValueError(f"User {user.username} already exists") from exc

    def update(self, user: User) -> None:
        values = {"password_hash": user.password_hash, "role": user.role.value, "active": user.active}
        result = self._connection.execute(
            update(users).where(users.c.username == user.username).values(values)
        )
        if result.rowcount == 0:
            raise KeyError(user.username)
