from datetime import timedelta

import pytest

from kuntur.domain.alerts import AlertCode, Severity
from kuntur.domain.devices import DeviceKind
from kuntur.domain.errors import DomainValidationError
from kuntur.domain.readings import FailureCause
from kuntur.domain.rules import (
    AlertEngine,
    ConfirmedFailureRule,
    CounterIncreaseRule,
    Direction,
    FlapGuard,
    RuleContext,
    ThresholdRule,
    Transition,
    Verdict,
    default_rules,
)
from tests.factories import at, failed, metric_stream, ok, replay, stream

HOT = ThresholdRule(
    AlertCode.UPS_BATTERY_HOT, Severity.WARNING, frozenset({DeviceKind.UPS}), "battery_temp_c",
    Direction.ABOVE, raise_at=40, clear_at=37, label="temperatura de batería", unit=" °C",
    confirm=3, window=4, clear_after=3,
)  # fmt: skip
LOW = ThresholdRule(
    AlertCode.UPS_BATTERY_LOW, Severity.CRITICAL, frozenset({DeviceKind.UPS}), "battery_charge_pct",
    Direction.BELOW, raise_at=20, clear_at=30, label="carga de batería", unit=" %",
)  # fmt: skip
IMPACTS = CounterIncreaseRule(
    AlertCode.BARRIER_IMPACT, Severity.WARNING, frozenset({DeviceKind.BARRIER}), "impacts_total",
    label="impactos", quiet_readings=2,
)  # fmt: skip


class TestConfirmedFailure:
    def test_an_isolated_failure_is_noise(self) -> None:
        assert replay(ConfirmedFailureRule(), stream([True, False, True, True, False, True])) == []

    def test_four_failures_out_of_five_raise_on_the_fourth(self) -> None:
        readings = stream([True, False, False, True, False, False])
        assert replay(ConfirmedFailureRule(), readings) == [(5, Transition.RAISE)]

    def test_the_message_names_the_dominant_cause(self) -> None:
        readings = [
            failed(0, cause=FailureCause.TIMEOUT),
            failed(1, cause=FailureCause.CONNECTION_REFUSED),
            failed(2, cause=FailureCause.TIMEOUT),
            failed(3, cause=FailureCause.TIMEOUT),
        ]
        verdict = ConfirmedFailureRule().evaluate(RuleContext(readings, None, None, at(3)))
        assert verdict.transition is Transition.RAISE
        assert "4 de las últimas 4" in verdict.message
        assert "TIMEOUT" in verdict.message

    def test_clears_only_after_two_answered_readings_in_a_row(self) -> None:
        readings = stream([False, False, False, False, True, False, True, True])
        assert replay(ConfirmedFailureRule(), readings) == [(3, Transition.RAISE), (7, Transition.CLEAR)]

    @pytest.mark.parametrize(("failures", "window"), [(0, 5), (6, 5)])
    def test_rejects_an_impossible_confirmation(self, failures: int, window: int) -> None:
        with pytest.raises(DomainValidationError):
            ConfirmedFailureRule(failures=failures, window=window)


class TestThreshold:
    def test_needs_confirmation_before_raising(self) -> None:
        readings = metric_stream("battery_temp_c", [41, 36, 42, 36, 43, 41, 42])
        assert replay(HOT, readings) == [(5, Transition.RAISE)]

    def test_hysteresis_keeps_the_alert_between_the_two_limits(self) -> None:
        readings = metric_stream("battery_temp_c", [41, 42, 43, 39, 38, 38.5, 39.9, 37, 36, 35])
        assert replay(HOT, readings) == [(2, Transition.RAISE), (9, Transition.CLEAR)]

    def test_below_direction_for_battery_charge(self) -> None:
        readings = metric_stream("battery_charge_pct", [50, 19, 18, 25, 28, 31, 35])
        assert replay(LOW, readings) == [(2, Transition.RAISE), (6, Transition.CLEAR)]

    def test_readings_without_the_metric_are_ignored(self) -> None:
        readings = [*metric_stream("battery_temp_c", [41, 42, 43]), failed(3), failed(4)]
        transitions = replay(HOT, readings)
        assert transitions == [(2, Transition.RAISE)]

    def test_message_reports_the_crossings_and_last_value(self) -> None:
        readings = metric_stream("battery_temp_c", [41, 42.5, 44])
        verdict = HOT.evaluate(RuleContext(readings, None, None, at(2)))
        assert (
            verdict.message
            == "Temperatura de batería sobre 40 °C en 3 de las últimas 3 lecturas (última: 44 °C)"
        )

    def test_a_state_flag_reads_as_a_sentence(self) -> None:
        on_battery = next(rule for rule in default_rules() if rule.code is AlertCode.UPS_ON_BATTERY)
        verdict = on_battery.evaluate(RuleContext(metric_stream("on_battery", [1, 1]), None, None, at(1)))
        assert verdict.message == (
            "UPS operando con batería: no llega energía de la red (en 2 de las últimas 2 lecturas)"
        )

    def test_the_label_keeps_its_acronyms(self) -> None:
        rule = ThresholdRule(
            AlertCode.UPS_BATTERY_HOT, Severity.WARNING, frozenset({DeviceKind.UPS}), "t", Direction.ABOVE,
            raise_at=40, clear_at=37, label="UPS caliente", confirm=1, window=1,
        )  # fmt: skip
        verdict = rule.evaluate(RuleContext(metric_stream("t", [41]), None, None, at(0)))
        assert verdict.message.startswith("UPS caliente sobre 40")

    @pytest.mark.parametrize(
        ("direction", "raise_at", "clear_at"), [(Direction.ABOVE, 40, 41), (Direction.BELOW, 20, 10)]
    )
    def test_rejects_inverted_hysteresis(
        self, direction: Direction, raise_at: float, clear_at: float
    ) -> None:
        with pytest.raises(DomainValidationError):
            ThresholdRule(
                AlertCode.UPS_BATTERY_HOT, Severity.WARNING, frozenset({DeviceKind.UPS}), "x", direction,
                raise_at=raise_at, clear_at=clear_at, label="x",
            )  # fmt: skip


class TestCounterIncrease:
    def test_raises_on_growth_and_clears_after_quiet_readings(self) -> None:
        readings = metric_stream("impacts_total", [3, 3, 4, 4, 4, 4], device_id="barrera-01")
        assert replay(IMPACTS, readings) == [(2, Transition.RAISE), (4, Transition.CLEAR)]

    def test_a_counter_reset_is_not_an_event(self) -> None:
        readings = metric_stream("impacts_total", [120, 0, 0], device_id="barrera-01")
        assert replay(IMPACTS, readings) == []

    def test_reports_how_many_new_events(self) -> None:
        readings = metric_stream("impacts_total", [3, 5], device_id="barrera-01")
        assert IMPACTS.evaluate(RuleContext(readings, None, None, at(1))).message == (
            "Impactos: 2 nuevo(s) desde la lectura anterior"
        )


class TestFlapGuard:
    def test_holds_a_clear_until_the_minimum_active_time(self) -> None:
        guarded = FlapGuard(ConfirmedFailureRule(), min_active=timedelta(seconds=30))
        readings = stream([False] * 4 + [True] * 8)
        # Raised at index 3 (t=15 s); the rule wants to clear at index 5 (t=25 s) but must wait until t>=45 s
        assert replay(guarded, readings) == [(3, Transition.RAISE), (9, Transition.CLEAR)]

    def test_holds_a_new_raise_during_the_cooldown(self) -> None:
        guarded = FlapGuard(ConfirmedFailureRule(), cooldown=timedelta(seconds=40))
        readings = stream([False] * 4 + [True] * 2 + [False] * 10)
        assert replay(guarded, readings) == [
            (3, Transition.RAISE),
            (5, Transition.CLEAR),
            (13, Transition.RAISE),
        ]

    def test_exposes_the_wrapped_rule_identity(self) -> None:
        guarded = FlapGuard(HOT)
        assert (guarded.code, guarded.severity) == (AlertCode.UPS_BATTERY_HOT, Severity.WARNING)
        assert guarded.applies_to(DeviceKind.UPS)
        assert not guarded.applies_to(DeviceKind.CAMERA)


class _AlwaysRaise:
    code = AlertCode.UPS_ON_BATTERY
    severity = Severity.CRITICAL

    def applies_to(self, kind: DeviceKind) -> bool:
        return True

    def evaluate(self, ctx: RuleContext) -> Verdict:
        return Verdict(Transition.RAISE, "siempre")


class TestAlertEngine:
    def test_only_runs_rules_for_the_device_kind(self) -> None:
        engine = AlertEngine((HOT, IMPACTS))
        readings = metric_stream("battery_temp_c", [45, 46, 47])
        decisions = engine.evaluate(DeviceKind.CAMERA, readings, {}, {}, at(2))
        assert decisions == []

    def test_never_raises_an_alert_that_is_already_active(self) -> None:
        engine = AlertEngine((_AlwaysRaise(),))
        assert engine.evaluate(DeviceKind.UPS, [ok(0)], {AlertCode.UPS_ON_BATTERY: at(0)}, {}, at(0)) == []
        decision = engine.evaluate(DeviceKind.UPS, [ok(0)], {}, {}, at(0))
        assert [(d.code, d.transition) for d in decision] == [(AlertCode.UPS_ON_BATTERY, Transition.RAISE)]

    def test_rejects_two_rules_for_the_same_code(self) -> None:
        with pytest.raises(DomainValidationError):
            AlertEngine((HOT, HOT))

    def test_default_rules_cover_every_alert_code_once(self) -> None:
        codes = [rule.code for rule in default_rules()]
        assert sorted(codes) == sorted(AlertCode)
        AlertEngine(default_rules())
