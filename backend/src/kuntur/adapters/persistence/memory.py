"""In-memory unit of work with real transaction semantics.

Every transaction works on copies and only ``commit()`` publishes them, so a use case that forgets to
call ``update()`` or fails half-way behaves exactly as it would against SQL Server. A lock serialises
transactions because the collector records readings from worker threads.
"""

from __future__ import annotations

import itertools
import threading
from collections import defaultdict
from dataclasses import replace
from datetime import datetime
from types import TracebackType
from typing import Self

from kuntur.application.ports import AlertRepository, CommandRepository, DeviceRepository, ReadingRepository
from kuntur.domain.alerts import Alert, AlertCode, AlertState
from kuntur.domain.commands import Command
from kuntur.domain.devices import Device
from kuntur.domain.readings import Reading


class InMemoryStore:
    """The committed state. Only ``InMemoryUnitOfWork`` should touch it."""

    def __init__(self, max_readings_per_device: int = 20_000) -> None:
        self.lock = threading.RLock()
        self.max_readings_per_device = max_readings_per_device
        self.devices: dict[str, Device] = {}
        self.readings: defaultdict[str, list[Reading]] = defaultdict(list)
        self.alerts: dict[str, Alert] = {}
        self.commands: dict[str, Command] = {}


class _Devices:
    def __init__(self, data: dict[str, Device]) -> None:
        self._data = data

    def get(self, device_id: str) -> Device | None:
        device = self._data.get(device_id)
        return replace(device) if device is not None else None

    def list(self, *, active_only: bool = False) -> list[Device]:
        devices = sorted(self._data.values(), key=lambda d: d.id)
        return [replace(d) for d in devices if d.active or not active_only]

    def add(self, device: Device) -> None:
        if device.id in self._data:
            raise ValueError(f"Device {device.id} already exists")
        self._data[device.id] = replace(device)

    def update(self, device: Device) -> None:
        if device.id not in self._data:
            raise KeyError(device.id)
        self._data[device.id] = replace(device)


class _Readings:
    """Readings are append-only and immutable, so new ones go to a pending list instead of copying
    the history on every transaction."""

    def __init__(self, stored: defaultdict[str, list[Reading]]) -> None:
        self._stored = stored
        self.pending: defaultdict[str, list[Reading]] = defaultdict(list)

    def _all(self, device_id: str) -> list[Reading]:
        return [*self._stored.get(device_id, ()), *self.pending.get(device_id, ())]

    def add(self, reading: Reading) -> None:
        self.pending[reading.device_id].append(reading)

    def recent(self, device_id: str, limit: int) -> list[Reading]:
        if limit <= 0:
            return []
        stored = self._stored.get(device_id, [])
        return [*stored[-limit:], *self.pending.get(device_id, ())][-limit:]

    def latest(self, device_id: str, *, answered_only: bool = False) -> Reading | None:
        newest_first = itertools.chain(
            reversed(self.pending.get(device_id, [])), reversed(self._stored.get(device_id, []))
        )
        return next((r for r in newest_first if r.answered or not answered_only), None)

    def history(self, device_id: str, since: datetime, limit: int) -> list[Reading]:
        return [r for r in self._all(device_id) if r.taken_at >= since][:limit]

    def average(self, device_id: str, metric: str, since: datetime) -> float | None:
        values = [
            v for r in self._all(device_id) if r.taken_at >= since and (v := r.metric(metric)) is not None
        ]
        return sum(values) / len(values) if values else None


class _Alerts:
    def __init__(self, data: dict[str, Alert]) -> None:
        self._data = data

    def add(self, alert: Alert) -> None:
        self._data[alert.id] = replace(alert)

    def update(self, alert: Alert) -> None:
        if alert.id not in self._data:
            raise KeyError(alert.id)
        self._data[alert.id] = replace(alert)

    def get(self, alert_id: str) -> Alert | None:
        alert = self._data.get(alert_id)
        return replace(alert) if alert is not None else None

    def active(self, device_id: str | None = None) -> list[Alert]:
        return [
            replace(a)
            for a in sorted(self._data.values(), key=lambda a: (a.raised_at, a.id))
            if a.is_active and (device_id is None or a.device_id == device_id)
        ]

    def last_resolved_at(self, device_id: str) -> dict[AlertCode, datetime]:
        latest: dict[AlertCode, datetime] = {}
        for alert in self._data.values():
            if alert.device_id == device_id and alert.resolved_at is not None:
                previous = latest.get(alert.code)
                if previous is None or alert.resolved_at > previous:
                    latest[alert.code] = alert.resolved_at
        return latest

    def search(self, *, state: AlertState | None, device_id: str | None, limit: int) -> list[Alert]:
        found = [
            a
            for a in sorted(self._data.values(), key=lambda a: (a.raised_at, a.id), reverse=True)
            if (state is None or a.state is state) and (device_id is None or a.device_id == device_id)
        ]
        return [replace(a) for a in found[:limit]]


class _Commands:
    def __init__(self, data: dict[str, Command]) -> None:
        self._data = data

    def add(self, command: Command) -> None:
        self._data[command.id] = replace(command)

    def update(self, command: Command) -> None:
        if command.id not in self._data:
            raise KeyError(command.id)
        self._data[command.id] = replace(command)

    def search(self, *, device_id: str | None, limit: int) -> list[Command]:
        found = [
            c
            for c in sorted(self._data.values(), key=lambda c: (c.requested_at, c.id), reverse=True)
            if device_id is None or c.device_id == device_id
        ]
        return [replace(c) for c in found[:limit]]


class InMemoryUnitOfWork:
    devices: DeviceRepository
    readings: ReadingRepository
    alerts: AlertRepository
    commands: CommandRepository

    def __init__(self, store: InMemoryStore) -> None:
        self._store = store

    def __enter__(self) -> Self:
        self._store.lock.acquire()
        self._begin()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        # Whatever was not committed is simply dropped with the working copies
        self._store.lock.release()

    def _begin(self) -> None:
        store = self._store
        self._devices = {k: replace(v) for k, v in store.devices.items()}
        self._alerts = {k: replace(v) for k, v in store.alerts.items()}
        self._commands = {k: replace(v) for k, v in store.commands.items()}
        self._readings = _Readings(store.readings)
        self.devices = _Devices(self._devices)
        self.readings = self._readings
        self.alerts = _Alerts(self._alerts)
        self.commands = _Commands(self._commands)

    def commit(self) -> None:
        store = self._store
        store.devices, store.alerts, store.commands = self._devices, self._alerts, self._commands
        for device_id, new in self._readings.pending.items():
            stored = store.readings[device_id]
            stored.extend(new)
            if len(stored) > store.max_readings_per_device:
                del stored[: len(stored) - store.max_readings_per_device]
        self._begin()

    def rollback(self) -> None:
        self._begin()
