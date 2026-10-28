from datetime import timedelta

from kuntur.adapters.metrics import Metrics
from kuntur.domain.alerts import Alert, AlertCode, Severity
from kuntur.domain.devices import DeviceKind
from kuntur.domain.events import AlertRaised, AlertResolved, ReadingRecorded
from kuntur.domain.health import Health
from tests.factories import T0, failed, ok


def _value(metrics: Metrics, name: str, **labels: str) -> float | None:
    return metrics.registry.get_sample_value(name, labels)


def test_readings_count_by_kind_status_and_cause() -> None:
    metrics = Metrics()
    metrics.handle(ReadingRecorded(T0, ok(0), Health.OK, DeviceKind.UPS, 0.04))
    metrics.handle(ReadingRecorded(T0, failed(1), Health.DEGRADED, DeviceKind.UPS, 3.0))
    assert _value(metrics, "kuntur_readings_total", kind="UPS", status="OK") == 1
    assert _value(metrics, "kuntur_read_problems_total", kind="UPS", cause="TIMEOUT") == 1
    assert _value(metrics, "kuntur_read_duration_seconds_count", kind="UPS") == 2


def test_the_active_alerts_gauge_follows_raise_and_resolve() -> None:
    metrics = Metrics()
    alert = Alert("a1", "ups-01", AlertCode.UPS_BATTERY_HOT, Severity.WARNING, "Caliente", T0)
    metrics.start_from([alert])
    assert _value(metrics, "kuntur_active_alerts", severity="WARNING") == 1
    metrics.handle(
        AlertRaised.of(Alert("a2", "ups-01", AlertCode.DEVICE_UNREACHABLE, Severity.CRITICAL, "x", T0))
    )
    alert.resolve(T0 + timedelta(minutes=10))
    metrics.handle(AlertResolved.of(alert))
    assert _value(metrics, "kuntur_active_alerts", severity="WARNING") == 0
    assert _value(metrics, "kuntur_active_alerts", severity="CRITICAL") == 1
    assert _value(metrics, "kuntur_alert_duration_seconds_sum", code="UPS_BATTERY_HOT") == 600
