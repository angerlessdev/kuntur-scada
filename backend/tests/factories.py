"""Builders shared by the tests: readable defaults, override only what the test is about."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta

from kuntur.domain.devices import Device, DeviceKind, Endpoint, LifetimeProfile
from kuntur.domain.readings import FailureCause, Reading
from kuntur.domain.rules import AlertRule, RuleContext, Transition

T0 = datetime(2026, 1, 15, 8, 0, tzinfo=UTC)
STEP = timedelta(seconds=5)


def at(index: int) -> datetime:
    return T0 + index * STEP


def ups(device_id: str = "ups-01", installed_on: date = date(2023, 1, 15), **overrides: object) -> Device:
    fields: dict[str, object] = {
        "id": device_id,
        "name": "UPS sala eléctrica",
        "kind": DeviceKind.UPS,
        "site": "Peaje Norte",
        "endpoint": Endpoint("127.0.0.1", 15020),
        "installed_on": installed_on,
        "lifetime": LifetimeProfile(design_life_years=10, battery_design_life_years=5),
    }
    fields.update(overrides)
    return Device(**fields)  # type: ignore[arg-type]


def barrier(device_id: str = "barrera-01", installed_on: date = date(2022, 6, 1)) -> Device:
    return Device(
        device_id,
        "Barrera vía 3",
        DeviceKind.BARRIER,
        "Peaje Norte",
        Endpoint("127.0.0.1", 15030),
        installed_on,
        LifetimeProfile(design_life_years=12, rated_cycles=5_000_000, rated_impacts=2_000),
    )


def camera(device_id: str = "camara-01") -> Device:
    return Device(
        device_id,
        "Cámara frontal vía 3",
        DeviceKind.CAMERA,
        "Peaje Norte",
        Endpoint("127.0.0.1", 15040, "/cameras/camara-01"),
        date(2024, 3, 1),
        LifetimeProfile(design_life_years=7),
    )


def ok(index: int, device_id: str = "ups-01", **metrics: float) -> Reading:
    return Reading.ok(device_id, at(index), metrics or {"load_pct": 40.0})


def failed(index: int, device_id: str = "ups-01", cause: FailureCause = FailureCause.TIMEOUT) -> Reading:
    return Reading.failed(device_id, at(index), cause)


def stream(flags: Iterable[bool], device_id: str = "ups-01") -> list[Reading]:
    """``True`` is an answered reading, ``False`` a failed one."""
    return [ok(i, device_id) if answered else failed(i, device_id) for i, answered in enumerate(flags)]


def metric_stream(name: str, values: Iterable[float], device_id: str = "ups-01") -> list[Reading]:
    return [Reading.ok(device_id, at(i), {name: v}) for i, v in enumerate(values)]


def replay(rule: AlertRule, readings: Sequence[Reading], window: int = 10) -> list[tuple[int, Transition]]:
    """Feeds readings to a rule one by one, keeping the alert state as the application would.
    Returns every effective transition as ``(index, RAISE|CLEAR)``."""
    transitions: list[tuple[int, Transition]] = []
    active_since: datetime | None = None
    last_resolved: datetime | None = None
    for i, reading in enumerate(readings):
        ctx = RuleContext(
            readings[max(0, i - window + 1) : i + 1], active_since, last_resolved, reading.taken_at
        )
        verdict = rule.evaluate(ctx)
        if verdict.transition is Transition.RAISE and active_since is None:
            active_since = reading.taken_at
            transitions.append((i, Transition.RAISE))
        elif verdict.transition is Transition.CLEAR and active_since is not None:
            active_since, last_resolved = None, reading.taken_at
            transitions.append((i, Transition.CLEAR))
    return transitions
