"""Properties of the alert rules, checked against thousands of generated sequences.

These are the guarantees an operator relies on, stated as code:

1. Noise never pages anyone: isolated failures do not raise an alert.
2. A real outage always does, within the confirmation window.
3. Between the two thresholds, the alert keeps its state (hysteresis).
4. The flap guard bounds how often an alert can change state.
5. The engine's decisions are always consistent with the current alert state.
"""

from __future__ import annotations

import itertools
from datetime import timedelta

from hypothesis import given, settings
from hypothesis import strategies as st

from kuntur.domain.alerts import AlertCode, Severity
from kuntur.domain.devices import DeviceKind
from kuntur.domain.lifetime import battery_clock, mechanical_clock
from kuntur.domain.rules import (
    AlertEngine,
    ConfirmedFailureRule,
    Direction,
    FlapGuard,
    ThresholdRule,
    Transition,
    default_rules,
)
from tests.factories import STEP, metric_stream, replay, stream

RULE = ConfirmedFailureRule(failures=4, window=5, recoveries=2)
HOT = ThresholdRule(
    AlertCode.UPS_BATTERY_HOT, Severity.WARNING, frozenset({DeviceKind.UPS}), "battery_temp_c",
    Direction.ABOVE, raise_at=40, clear_at=37, label="temperatura", confirm=3, window=4, clear_after=3,
)  # fmt: skip


def _max_failures_in_any_window(flags: list[bool], window: int) -> int:
    return max(
        (flags[i : i + window].count(False) for i in range(max(1, len(flags) - window + 1))), default=0
    )


@given(st.lists(st.booleans(), max_size=60))
def test_no_alert_unless_some_window_holds_enough_failures(flags: list[bool]) -> None:
    raised = any(t is Transition.RAISE for _, t in replay(RULE, stream(flags)))
    if _max_failures_in_any_window(flags, RULE.window) < RULE.failures:
        assert not raised


@given(st.lists(st.booleans(), max_size=40))
def test_a_sustained_outage_always_raises_within_the_confirmation(prefix: list[bool]) -> None:
    flags = [*prefix, *([False] * RULE.failures)]
    transitions = replay(RULE, stream(flags))
    state_at_end = transitions[-1][1] if transitions else Transition.CLEAR
    assert state_at_end is Transition.RAISE


@given(
    st.lists(st.floats(min_value=37.01, max_value=39.99, allow_nan=False), min_size=1, max_size=40),
)
def test_values_between_the_thresholds_never_change_the_state(middle: list[float]) -> None:
    raised = [41.0, 42.0, 43.0]
    transitions = replay(HOT, metric_stream("battery_temp_c", [*raised, *middle]))
    assert transitions == [(2, Transition.RAISE)]


@settings(max_examples=200)
@given(st.lists(st.booleans(), max_size=80), st.integers(min_value=1, max_value=12))
def test_flap_guard_keeps_a_minimum_time_in_each_state(flags: list[bool], hold_steps: int) -> None:
    hold = hold_steps * STEP
    guarded = FlapGuard(RULE, min_active=hold, cooldown=hold)
    transitions = replay(guarded, stream(flags))
    for (i, _), (j, _) in itertools.pairwise(transitions):
        assert (j - i) * STEP >= hold


@given(st.lists(st.booleans(), max_size=60))
def test_transitions_always_alternate(flags: list[bool]) -> None:
    kinds = [t for _, t in replay(RULE, stream(flags))]
    assert all(a is not b for a, b in itertools.pairwise(kinds))
    if kinds:
        assert kinds[0] is Transition.RAISE


@given(
    st.lists(st.booleans(), min_size=1, max_size=20),
    st.sets(st.sampled_from(list(AlertCode))),
)
def test_engine_decisions_are_consistent_with_the_alert_state(
    flags: list[bool], active: set[AlertCode]
) -> None:
    readings = stream(flags)
    now = readings[-1].taken_at
    engine = AlertEngine(default_rules(min_active=timedelta(0), cooldown=timedelta(0)))
    for decision in engine.evaluate(DeviceKind.UPS, readings, dict.fromkeys(active, now), {}, now):
        if decision.transition is Transition.RAISE:
            assert decision.code not in active
        else:
            assert decision.code in active


@given(
    st.integers(min_value=1, max_value=4000),
    st.floats(min_value=0, max_value=60),
    st.floats(min_value=0, max_value=60),
)
def test_a_hotter_battery_never_lasts_longer(age: int, t1: float, t2: float) -> None:
    cool, hot = sorted((t1, t2))
    assert battery_clock(age, hot, 5).consumed >= battery_clock(age, cool, 5).consumed


@given(
    st.integers(min_value=0, max_value=10_000_000),
    st.integers(min_value=0, max_value=5_000),
    st.integers(min_value=0, max_value=5_000),
)
def test_more_impacts_never_reduce_the_damage(cycles: int, impacts: int, extra: int) -> None:
    base = mechanical_clock(cycles, impacts, 5_000_000, 2_000, age_days=1000)
    worse = mechanical_clock(cycles, impacts + extra, 5_000_000, 2_000, age_days=1000)
    assert worse.consumed >= base.consumed
