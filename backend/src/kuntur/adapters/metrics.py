"""Prometheus metrics, fed by the domain events.

Labels are closed sets (kind, status, cause, code, severity): never a device id, which would grow the
series without bound. The read duration is there to calibrate timeouts from evidence, not by eye.
"""

from __future__ import annotations

from collections.abc import Iterable

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

from kuntur.domain.alerts import Alert, Severity
from kuntur.domain.events import AlertRaised, AlertResolved, CommandFinished, DomainEvent, ReadingRecorded


class Metrics:
    def __init__(self, registry: CollectorRegistry | None = None) -> None:
        self.registry = registry or CollectorRegistry()
        r = self.registry
        self.readings = Counter("kuntur_readings_total", "Readings recorded", ["kind", "status"], registry=r)
        self.read_problems = Counter(
            "kuntur_read_problems_total",
            "Failed or partial readings, by cause",
            ["kind", "cause"],
            registry=r,
        )
        self.read_duration = Histogram(
            "kuntur_read_duration_seconds",
            "Time a driver took to read a device",
            ["kind"],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5),
            registry=r,
        )
        self.alerts_raised = Counter(
            "kuntur_alerts_raised_total", "Alerts raised", ["code", "severity"], registry=r
        )
        self.active_alerts = Gauge("kuntur_active_alerts", "Alerts active now", ["severity"], registry=r)
        self.alert_duration = Histogram(
            "kuntur_alert_duration_seconds",
            "How long alerts stayed active",
            ["code"],
            buckets=(30, 60, 300, 900, 3600, 4 * 3600, 24 * 3600),
            registry=r,
        )
        self.commands = Counter("kuntur_commands_total", "Commands finished", ["kind", "status"], registry=r)

    def start_from(self, active: Iterable[Alert]) -> None:
        """Seeds the active-alerts gauge with what is already open when the process starts."""
        counts = dict.fromkeys(Severity, 0)
        for alert in active:
            counts[alert.severity] += 1
        for severity, count in counts.items():
            self.active_alerts.labels(severity.value).set(count)

    def handle(self, event: DomainEvent) -> None:
        match event:
            case ReadingRecorded(reading=reading, kind=kind, elapsed_s=elapsed_s):
                self.readings.labels(kind.value, reading.status.value).inc()
                if reading.cause is not None:
                    self.read_problems.labels(kind.value, reading.cause.value).inc()
                if elapsed_s is not None:
                    self.read_duration.labels(kind.value).observe(elapsed_s)
            case AlertRaised(alert=alert):
                self.alerts_raised.labels(alert.code.value, alert.severity.value).inc()
                self.active_alerts.labels(alert.severity.value).inc()
            case AlertResolved(alert=alert, occurred_at=resolved_at):
                self.active_alerts.labels(alert.severity.value).dec()
                self.alert_duration.labels(alert.code.value).observe(
                    alert.duration(resolved_at).total_seconds()
                )
            case CommandFinished(command=command):
                self.commands.labels(command.kind.value, command.status.value).inc()
            case _:
                pass
