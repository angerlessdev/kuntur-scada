"""Incident contexts for the narrator tests and the evals: one per kind of alert, with readings that
carry exactly the numbers a good explanation should quote."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import timedelta

from kuntur.application.ports import IncidentContext
from kuntur.domain.alerts import Alert, AlertCode, Severity
from kuntur.domain.commands import ALLOWED_COMMANDS
from kuntur.domain.devices import Device
from kuntur.domain.readings import FailureCause, Reading
from tests.factories import T0, at, barrier, camera, ups


def incident(
    device: Device,
    code: AlertCode,
    readings: Sequence[Reading],
    *,
    severity: Severity = Severity.CRITICAL,
    message: str = "Alerta",
    previous_alerts: int = 0,
) -> IncidentContext:
    alert = Alert("alerta-1", device.id, code, severity, message, readings[-1].taken_at)
    causes = Counter(r.cause for r in readings if r.cause is not None)
    allowed = tuple(sorted(ALLOWED_COMMANDS[device.kind]))
    return IncidentContext(
        alert, device, tuple(readings), dict(causes), previous_alerts, (), allowed, readings[-1].taken_at
    )


def failures(device_id: str, cause: FailureCause, count: int = 4, detail: str | None = None) -> list[Reading]:
    return [Reading.ok(device_id, T0, {"x": 1.0})] + [
        Reading.failed(device_id, at(i + 1), cause, detail) for i in range(count)
    ]


def lost_contact(cause: FailureCause = FailureCause.CONNECTION_REFUSED) -> IncidentContext:
    return incident(ups(), AlertCode.DEVICE_UNREACHABLE, failures("ups-01", cause))


def on_battery() -> IncidentContext:
    readings = [
        Reading.ok("ups-01", at(i), {"on_battery": 1.0, "autonomy_min": 18.0, "battery_charge_pct": 87.0})
        for i in range(3)
    ]
    return incident(ups(), AlertCode.UPS_ON_BATTERY, readings)


def battery_low() -> IncidentContext:
    readings = [
        Reading.ok("ups-01", at(i), {"on_battery": 1.0, "autonomy_min": 3.0, "battery_charge_pct": 15.0})
        for i in range(3)
    ]
    return incident(ups(), AlertCode.UPS_BATTERY_LOW, readings)


def battery_hot() -> IncidentContext:
    readings = [Reading.ok("ups-01", at(i), {"battery_temp_c": 44.0}) for i in range(4)]
    return incident(ups(), AlertCode.UPS_BATTERY_HOT, readings, severity=Severity.WARNING)


def barrier_impact() -> IncidentContext:
    readings = [
        Reading.ok("barrera-01", at(0), {"impacts_total": 41.0, "cycles_total": 1_650_000.0}),
        Reading.ok("barrera-01", at(1), {"impacts_total": 42.0, "cycles_total": 1_650_003.0}),
    ]
    return incident(barrier(), AlertCode.BARRIER_IMPACT, readings, severity=Severity.WARNING)


def clock_drift() -> IncidentContext:
    readings = [
        Reading.ok("camara-01", at(i), {"clock_offset_s": 612.0, "clock_drift_s": 612.0}) for i in range(3)
    ]
    return incident(camera(), AlertCode.CAMERA_CLOCK_DRIFT, readings, severity=Severity.WARNING)


def one_hour_later(context: IncidentContext) -> IncidentContext:
    return IncidentContext(
        context.alert,
        context.device,
        context.recent_readings,
        context.failure_causes,
        context.previous_alerts,
        context.recent_commands,
        context.allowed_commands,
        context.now + timedelta(hours=1),
    )
