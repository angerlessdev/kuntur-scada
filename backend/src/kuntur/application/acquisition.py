"""Acquisition use cases: record a reading (and react to it), poll a device."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from kuntur.application.ports import Clock, DriverRegistry, EventPublisher, IdGenerator, UnitOfWorkFactory
from kuntur.domain.alerts import Alert, AlertCode
from kuntur.domain.devices import Device
from kuntur.domain.errors import NotFoundError
from kuntur.domain.events import AlertRaised, AlertResolved, DomainEvent, ReadingRecorded
from kuntur.domain.health import Health, assess_health
from kuntur.domain.readings import FailureCause, Reading
from kuntur.domain.rules import AlertEngine, Transition

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RecordReading:
    """Stores a reading and applies the rule engine's decisions in the same transaction.
    Events go out only after the commit, so listeners never see something that was rolled back."""

    uow_factory: UnitOfWorkFactory
    engine: AlertEngine
    publisher: EventPublisher
    ids: IdGenerator
    window: int = 10

    def __call__(self, reading: Reading, *, elapsed_s: float | None = None) -> Health:
        events: list[DomainEvent] = []
        with self.uow_factory() as uow:
            device = uow.devices.get(reading.device_id)
            if device is None:
                raise NotFoundError(f"Unknown device {reading.device_id}")
            uow.readings.add(reading)
            window = uow.readings.recent(device.id, self.window)
            active: dict[AlertCode, Alert] = {alert.code: alert for alert in uow.alerts.active(device.id)}
            decisions = self.engine.evaluate(
                device.kind,
                window,
                {code: alert.raised_at for code, alert in active.items()},
                uow.alerts.last_resolved_at(device.id),
                reading.taken_at,
            )
            for decision in decisions:
                if decision.transition is Transition.RAISE:
                    alert = Alert(
                        self.ids.new_id(),
                        device.id,
                        decision.code,
                        decision.severity,
                        decision.message,
                        reading.taken_at,
                    )
                    uow.alerts.add(alert)
                    active[decision.code] = alert
                    events.append(AlertRaised.of(alert))
                else:
                    alert = active.pop(decision.code)
                    alert.resolve(reading.taken_at)
                    uow.alerts.update(alert)
                    events.append(AlertResolved.of(alert))
            health = assess_health(reading, active.values())
            uow.commit()
        recorded = ReadingRecorded(reading.taken_at, reading, health, device.kind, elapsed_s)
        self.publisher.publish([recorded, *events])
        return health


@dataclass(frozen=True, slots=True)
class PollDevice:
    """Reads one device through its protocol driver and records the result. A driver that hangs is
    cut off by ``timeout_s``; one that crashes is recorded as an UNKNOWN failure, never lost."""

    drivers: DriverRegistry
    record: RecordReading
    clock: Clock
    timeout_s: float = 5.0

    async def __call__(self, device: Device) -> Health:
        at = self.clock.now()
        driver = self.drivers.for_kind(device.kind)
        loop = asyncio.get_running_loop()
        started = loop.time()
        try:
            reading = await asyncio.wait_for(driver.read(device, at), self.timeout_s)
        except TimeoutError:
            reading = Reading.failed(
                device.id, at, FailureCause.TIMEOUT, f"Sin respuesta en {self.timeout_s:g} s"
            )
        except Exception as exc:  # the driver broke its contract: keep the evidence, do not stop polling
            logger.exception("Driver for %s crashed", device.id)
            reading = Reading.failed(device.id, at, FailureCause.UNKNOWN, type(exc).__name__)
        return await asyncio.to_thread(self.record, reading, elapsed_s=loop.time() - started)
