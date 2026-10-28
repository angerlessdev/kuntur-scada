"""Read side: what the screens show. No business decisions are taken here."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from kuntur.application.ports import Clock, UnitOfWork, UnitOfWorkFactory
from kuntur.domain.alerts import Alert, AlertState
from kuntur.domain.commands import Command
from kuntur.domain.devices import Device, DeviceKind
from kuntur.domain.errors import NotFoundError
from kuntur.domain.health import Health, assess_health
from kuntur.domain.lifetime import RemainingLife, remaining_life
from kuntur.domain.readings import Reading


@dataclass(frozen=True, slots=True)
class DeviceOverview:
    device: Device
    health: Health
    last_reading: Reading | None
    active_alerts: Sequence[Alert]
    life: RemainingLife
    today: date

    @property
    def replacement_date(self) -> date | None:
        return self.life.replacement_date(self.today)


@dataclass(frozen=True, slots=True)
class FleetQueries:
    uow_factory: UnitOfWorkFactory
    clock: Clock
    battery_temperature_window: timedelta = field(default=timedelta(days=7))

    def overview(self) -> list[DeviceOverview]:
        with self.uow_factory() as uow:
            return [self._overview(uow, device) for device in uow.devices.list(active_only=True)]

    def device(self, device_id: str) -> DeviceOverview:
        with self.uow_factory() as uow:
            return self._overview(uow, self._device(uow, device_id))

    def readings(self, device_id: str, since: datetime | None, limit: int) -> list[Reading]:
        with self.uow_factory() as uow:
            self._device(uow, device_id)
            if since is None:
                return uow.readings.recent(device_id, limit)
            return uow.readings.history(device_id, since, limit)

    def alerts(self, *, state: AlertState | None, device_id: str | None, limit: int) -> list[Alert]:
        with self.uow_factory() as uow:
            return uow.alerts.search(state=state, device_id=device_id, limit=limit)

    def alert(self, alert_id: str) -> Alert:
        with self.uow_factory() as uow:
            alert = uow.alerts.get(alert_id)
        if alert is None:
            raise NotFoundError(f"Unknown alert {alert_id}")
        return alert

    def commands(self, *, device_id: str | None, limit: int) -> list[Command]:
        with self.uow_factory() as uow:
            return uow.commands.search(device_id=device_id, limit=limit)

    @staticmethod
    def _device(uow: UnitOfWork, device_id: str) -> Device:
        device = uow.devices.get(device_id)
        if device is None:
            raise NotFoundError(f"Unknown device {device_id}")
        return device

    def _overview(self, uow: UnitOfWork, device: Device) -> DeviceOverview:
        now = self.clock.now()
        last = uow.readings.latest(device.id)
        last_answered = (
            last if last is not None and last.answered else uow.readings.latest(device.id, answered_only=True)
        )
        active = uow.alerts.active(device.id)
        avg_temp = None
        if device.kind is DeviceKind.UPS:
            avg_temp = uow.readings.average(
                device.id, "battery_temp_c", now - self.battery_temperature_window
            )
        life = remaining_life(
            device,
            now.date(),
            last_answered.metrics if last_answered is not None else None,
            avg_temp,
        )
        return DeviceOverview(device, assess_health(last, active), last, active, life, now.date())
