import pytest

from kuntur.domain.alerts import AlertCode, AlertState, Severity
from kuntur.domain.devices import DeviceKind
from kuntur.domain.errors import NotFoundError
from kuntur.domain.events import AlertRaised, AlertResolved, ReadingRecorded
from kuntur.domain.health import Health
from kuntur.domain.readings import FailureCause, Reading
from kuntur.domain.rules import RuleContext, Verdict
from tests.factories import at, barrier, failed, ok, ups
from tests.fakes import build_app


def test_a_complete_reading_is_stored_and_reported_healthy() -> None:
    app = build_app(ups())
    assert app.record(ok(0)) is Health.OK
    with app.uow() as uow:
        assert uow.readings.recent("ups-01", 10) == [ok(0)]
    [event] = app.bus.events
    assert isinstance(event, ReadingRecorded)
    assert event.health is Health.OK


def test_an_unknown_device_is_rejected_and_nothing_is_stored() -> None:
    app = build_app()
    with pytest.raises(NotFoundError):
        app.record(ok(0, device_id="fantasma"))
    assert app.store.readings == {}
    assert app.bus.events == []


def test_a_partial_reading_is_never_green() -> None:
    app = build_app(ups())
    reading = Reading.partial("ups-01", at(0), {"load_pct": 40.0}, FailureCause.INVALID_DATA, "temperatura")
    assert app.record(reading) is Health.DEGRADED


def test_an_isolated_failure_is_yellow_and_raises_nothing() -> None:
    app = build_app(ups())
    app.record(ok(0))
    assert app.record(failed(1)) is Health.DEGRADED
    assert app.queries.alerts(state=AlertState.ACTIVE, device_id=None, limit=10) == []


class TestConfirmedLossOfContact:
    def test_raises_one_critical_alert_and_turns_red(self) -> None:
        app = build_app(ups())
        healths = [app.record(failed(i)) for i in range(6)]
        assert healths == [Health.DEGRADED] * 3 + [Health.DOWN] * 3
        with app.uow() as uow:
            [alert] = uow.alerts.active("ups-01")
        assert (alert.code, alert.severity, alert.raised_at) == (
            AlertCode.DEVICE_UNREACHABLE,
            Severity.CRITICAL,
            at(3),
        )
        assert "4 de las últimas 4" in alert.message

    def test_more_failures_do_not_duplicate_the_alert(self) -> None:
        app = build_app(ups())
        for i in range(20):
            app.record(failed(i))
        assert len(app.queries.alerts(state=None, device_id="ups-01", limit=100)) == 1
        assert len(app.bus.of_type(AlertRaised)) == 1

    def test_clears_only_after_the_minimum_active_time(self) -> None:
        app = build_app(ups())
        for i in range(4):
            app.record(failed(i))
        healths = [app.record(ok(i)) for i in range(4, 10)]
        # Two answers (t=25 s) satisfy the rule, but the alert raised at t=15 s must last 30 s
        assert healths == [Health.DOWN] * 5 + [Health.OK]
        [resolved] = app.bus.of_type(AlertResolved)
        assert resolved.alert.resolved_at == at(9)
        assert resolved.occurred_at == at(9)

    def test_the_reading_is_announced_before_the_alert(self) -> None:
        app = build_app(ups())
        for i in range(4):
            app.record(failed(i))
        assert [type(e) for e in app.bus.events] == [ReadingRecorded] * 4 + [AlertRaised]


def test_alerts_from_different_rules_live_side_by_side() -> None:
    app = build_app(ups())
    for i in range(3):
        app.record(ok(i, on_battery=1, battery_charge_pct=15))
    active = app.queries.alerts(state=AlertState.ACTIVE, device_id="ups-01", limit=10)
    assert {a.code for a in active} == {AlertCode.UPS_ON_BATTERY, AlertCode.UPS_BATTERY_LOW}


def test_a_barrier_impact_comes_from_its_counter() -> None:
    app = build_app(barrier())
    app.record(ok(0, "barrera-01", cycles_total=1000, impacts_total=3))
    app.record(ok(1, "barrera-01", cycles_total=1010, impacts_total=4))
    [alert] = app.queries.alerts(state=AlertState.ACTIVE, device_id="barrera-01", limit=10)
    assert alert.code is AlertCode.BARRIER_IMPACT
    assert alert.message == "Impactos en la barrera: 1 nuevo(s) desde la lectura anterior"


class _BrokenRule:
    code = AlertCode.UPS_BATTERY_HOT
    severity = Severity.WARNING

    def applies_to(self, kind: DeviceKind) -> bool:
        return True

    def evaluate(self, ctx: RuleContext) -> Verdict:
        raise RuntimeError("bug en una regla")


def test_a_failed_transaction_stores_nothing_and_announces_nothing() -> None:
    app = build_app(ups(), rules=[_BrokenRule()])
    with pytest.raises(RuntimeError):
        app.record(ok(0))
    with app.uow() as uow:
        assert uow.readings.latest("ups-01") is None
    assert app.bus.events == []
