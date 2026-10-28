"""Alert rules: when to raise an alert and when to clear it.

Three mechanisms keep alerts trustworthy:

* **Confirmation (k of n):** one bad sample is noise; ``k`` bad samples among the last ``n`` is a fact.
* **Hysteresis:** an alert raised above a threshold clears only below a lower one, so a value
  hovering around the limit does not toggle it.
* **Flap guard:** a decorator that enforces a minimum time in each state.

Rules are strategies (``AlertRule``) and the engine only orchestrates them, so a new rule is a new
class, never an edit to the engine.
"""

from __future__ import annotations

import itertools
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from kuntur.domain.alerts import AlertCode, Severity
from kuntur.domain.devices import DeviceKind
from kuntur.domain.errors import DomainValidationError
from kuntur.domain.readings import CAUSE_LABELS, FailureCause, Reading, ReadingStatus


class Transition(StrEnum):
    RAISE = "RAISE"
    CLEAR = "CLEAR"
    HOLD = "HOLD"


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Everything a rule may look at. ``window`` is ordered oldest first; its last item is the newest."""

    window: Sequence[Reading]
    active_since: datetime | None
    last_resolved_at: datetime | None
    now: datetime
    expected_down_until: datetime | None = None
    """An operator's command took the device down on purpose (a reboot) until this time."""

    @property
    def is_active(self) -> bool:
        return self.active_since is not None

    @property
    def expected_down(self) -> bool:
        return self.expected_down_until is not None and self.now < self.expected_down_until


@dataclass(frozen=True, slots=True)
class Verdict:
    transition: Transition
    message: str = ""

    @classmethod
    def hold(cls) -> Verdict:
        return cls(Transition.HOLD)


class AlertRule(Protocol):
    @property
    def code(self) -> AlertCode: ...

    @property
    def severity(self) -> Severity: ...

    def applies_to(self, kind: DeviceKind) -> bool: ...

    def evaluate(self, ctx: RuleContext) -> Verdict: ...


def _check_window(confirm: int, window: int) -> None:
    if not 1 <= confirm <= window:
        raise DomainValidationError(f"Confirmation must be between 1 and the window ({confirm} of {window})")


def _sentence(text: str) -> str:
    """Upper-cases the first letter only: ``str.capitalize`` would turn "UPS" into "Ups"."""
    return text[:1].upper() + text[1:]


@dataclass(frozen=True, slots=True)
class ConfirmedFailureRule:
    """Raise when at least ``failures`` of the last ``window`` readings failed; clear after
    ``recoveries`` consecutive answered readings."""

    code: AlertCode = AlertCode.DEVICE_UNREACHABLE
    severity: Severity = Severity.CRITICAL
    failures: int = 4
    window: int = 5
    recoveries: int = 2

    def __post_init__(self) -> None:
        _check_window(self.failures, self.window)
        if self.recoveries < 1:
            raise DomainValidationError("At least one recovery reading is needed to clear")

    def applies_to(self, kind: DeviceKind) -> bool:
        return True

    def evaluate(self, ctx: RuleContext) -> Verdict:
        if ctx.is_active:
            latest = ctx.window[-self.recoveries :]
            recovered = len(latest) == self.recoveries and all(r.answered for r in latest)
            return Verdict(Transition.CLEAR) if recovered else Verdict.hold()

        if ctx.expected_down:  # a commanded reboot is not a loss of contact, until it takes too long
            return Verdict.hold()
        recent = ctx.window[-self.window :]
        failed = [r for r in recent if r.status is ReadingStatus.FAILED]
        if len(failed) < self.failures:
            return Verdict.hold()
        causes = Counter(r.cause for r in failed if r.cause is not None)
        cause = causes.most_common(1)[0][0] if causes else FailureCause.UNKNOWN
        message = f"Sin comunicación: {len(failed)} de las últimas {len(recent)} lecturas fallaron"
        return Verdict(Transition.RAISE, f"{message} ({CAUSE_LABELS[cause]})")


class Direction(StrEnum):
    ABOVE = "ABOVE"
    BELOW = "BELOW"


@dataclass(frozen=True, slots=True)
class ThresholdRule:
    """Raise when ``metric`` crosses ``raise_at`` in ``confirm`` of the last ``window`` samples; clear
    when the last ``clear_after`` samples are back past ``clear_at``. Readings without the metric
    (a device that did not answer) are ignored: losing contact is another rule's job."""

    code: AlertCode
    severity: Severity
    kinds: frozenset[DeviceKind]
    metric: str
    direction: Direction
    raise_at: float
    clear_at: float
    label: str
    unit: str = ""
    confirm: int = 2
    window: int = 3
    clear_after: int = 2
    summary: str = ""
    """Fixed wording for 0/1 state flags, where "above 1" would mean nothing to an operator."""

    def __post_init__(self) -> None:
        _check_window(self.confirm, self.window)
        if self.clear_after < 1:
            raise DomainValidationError("At least one sample is needed to clear")
        if self.direction is Direction.ABOVE:
            inverted = self.clear_at >= self.raise_at
        else:
            inverted = self.clear_at <= self.raise_at
        if inverted:
            raise DomainValidationError(
                f"Hysteresis is inverted for {self.metric}: clear_at must be on the safe side of raise_at"
            )

    def applies_to(self, kind: DeviceKind) -> bool:
        return kind in self.kinds

    def _crossed(self, value: float) -> bool:
        return value >= self.raise_at if self.direction is Direction.ABOVE else value <= self.raise_at

    def _back_to_normal(self, value: float) -> bool:
        return value <= self.clear_at if self.direction is Direction.ABOVE else value >= self.clear_at

    def evaluate(self, ctx: RuleContext) -> Verdict:
        values = [v for r in ctx.window if (v := r.metric(self.metric)) is not None]
        if ctx.is_active:
            latest = values[-self.clear_after :]
            normal = len(latest) == self.clear_after and all(self._back_to_normal(v) for v in latest)
            return Verdict(Transition.CLEAR) if normal else Verdict.hold()

        recent = values[-self.window :]
        crossings = sum(1 for v in recent if self._crossed(v))
        if crossings < self.confirm:
            return Verdict.hold()
        if self.summary:
            return Verdict(
                Transition.RAISE, f"{self.summary} (en {crossings} de las últimas {len(recent)} lecturas)"
            )
        side = "sobre" if self.direction is Direction.ABOVE else "bajo"
        return Verdict(
            Transition.RAISE,
            f"{_sentence(self.label)} {side} {self.raise_at:g}{self.unit} en {crossings} de las últimas "
            f"{len(recent)} lecturas (última: {recent[-1]:g}{self.unit})",
        )


@dataclass(frozen=True, slots=True)
class CounterIncreaseRule:
    """Raise when a monotonic counter (e.g. impacts) grows between two answered readings; clear after
    ``quiet_readings`` answered readings without growth. A counter that goes down is a device reset,
    not an event."""

    code: AlertCode
    severity: Severity
    kinds: frozenset[DeviceKind]
    counter: str
    label: str
    quiet_readings: int = 6

    def __post_init__(self) -> None:
        if self.quiet_readings < 1:
            raise DomainValidationError("At least one quiet reading is needed to clear")

    def applies_to(self, kind: DeviceKind) -> bool:
        return kind in self.kinds

    def evaluate(self, ctx: RuleContext) -> Verdict:
        values = [v for r in ctx.window if (v := r.metric(self.counter)) is not None]
        if ctx.is_active:
            latest = values[-(self.quiet_readings + 1) :]
            quiet = len(latest) == self.quiet_readings + 1 and all(
                later <= earlier for earlier, later in itertools.pairwise(latest)
            )
            return Verdict(Transition.CLEAR) if quiet else Verdict.hold()

        if len(values) < 2:  # noqa: PLR2004 - a growth needs two samples
            return Verdict.hold()
        growth = values[-1] - values[-2]
        if growth <= 0:
            return Verdict.hold()
        message = f"{_sentence(self.label)}: {growth:g} nuevo(s) desde la lectura anterior"
        return Verdict(Transition.RAISE, message)


@dataclass(frozen=True, slots=True)
class FlapGuard:
    """Decorator that keeps an alert active for at least ``min_active`` and keeps it quiet for at
    least ``cooldown`` after it clears, whatever the wrapped rule says."""

    rule: AlertRule
    min_active: timedelta = timedelta(0)
    cooldown: timedelta = timedelta(0)

    @property
    def code(self) -> AlertCode:
        return self.rule.code

    @property
    def severity(self) -> Severity:
        return self.rule.severity

    def applies_to(self, kind: DeviceKind) -> bool:
        return self.rule.applies_to(kind)

    def evaluate(self, ctx: RuleContext) -> Verdict:
        verdict = self.rule.evaluate(ctx)
        if (
            verdict.transition is Transition.CLEAR
            and ctx.active_since is not None
            and ctx.now - ctx.active_since < self.min_active
        ):
            return Verdict.hold()
        if (
            verdict.transition is Transition.RAISE
            and ctx.last_resolved_at is not None
            and ctx.now - ctx.last_resolved_at < self.cooldown
        ):
            return Verdict.hold()
        return verdict


@dataclass(frozen=True, slots=True)
class Decision:
    """What the application has to do: raise a new alert or clear the active one."""

    code: AlertCode
    transition: Transition
    severity: Severity
    message: str = ""


@dataclass(frozen=True, slots=True)
class AlertEngine:
    """Runs every applicable rule and returns only consistent decisions (never raises an alert that is
    already active, never clears one that is not)."""

    rules: Sequence[AlertRule] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        codes = [rule.code for rule in self.rules]
        if len(codes) != len(set(codes)):
            raise DomainValidationError("Each alert code can belong to one rule only")

    def evaluate(
        self,
        kind: DeviceKind,
        window: Sequence[Reading],
        active_since: Mapping[AlertCode, datetime],
        last_resolved_at: Mapping[AlertCode, datetime],
        now: datetime,
        *,
        expected_down_until: datetime | None = None,
    ) -> list[Decision]:
        decisions: list[Decision] = []
        for rule in self.rules:
            if not rule.applies_to(kind):
                continue
            ctx = RuleContext(
                window, active_since.get(rule.code), last_resolved_at.get(rule.code), now, expected_down_until
            )
            verdict = rule.evaluate(ctx)
            wanted = (verdict.transition is Transition.RAISE and not ctx.is_active) or (
                verdict.transition is Transition.CLEAR and ctx.is_active
            )
            if wanted:
                decisions.append(Decision(rule.code, verdict.transition, rule.severity, verdict.message))
        return decisions


def default_rules(
    *, min_active: timedelta = timedelta(seconds=30), cooldown: timedelta = timedelta(seconds=30)
) -> tuple[AlertRule, ...]:
    """The standard rule set. Every number here is a documented, tested decision."""
    ups = frozenset({DeviceKind.UPS})

    def guarded(rule: AlertRule) -> AlertRule:
        return FlapGuard(rule, min_active=min_active, cooldown=cooldown)

    return (
        guarded(ConfirmedFailureRule()),
        guarded(
            ThresholdRule(
                AlertCode.UPS_ON_BATTERY,
                Severity.CRITICAL,
                ups,
                "on_battery",
                Direction.ABOVE,
                raise_at=1,
                clear_at=0,
                label="UPS en batería",
                confirm=2,
                window=3,
                clear_after=2,
                summary="UPS operando con batería: no llega energía de la red",
            )
        ),
        guarded(
            ThresholdRule(
                AlertCode.UPS_BATTERY_LOW,
                Severity.CRITICAL,
                ups,
                "battery_charge_pct",
                Direction.BELOW,
                raise_at=20,
                clear_at=30,
                label="carga de batería",
                unit=" %",
                confirm=2,
                window=3,
                clear_after=2,
            )
        ),
        guarded(
            ThresholdRule(
                AlertCode.UPS_BATTERY_HOT,
                Severity.WARNING,
                ups,
                "battery_temp_c",
                Direction.ABOVE,
                raise_at=40,
                clear_at=37,
                label="temperatura de batería",
                unit=" °C",
                confirm=3,
                window=4,
                clear_after=3,
            )
        ),
        guarded(
            CounterIncreaseRule(
                AlertCode.BARRIER_IMPACT,
                Severity.WARNING,
                frozenset({DeviceKind.BARRIER}),
                "impacts_total",
                label="impactos en la barrera",
            )
        ),
        guarded(
            ThresholdRule(
                AlertCode.CAMERA_CLOCK_DRIFT,
                Severity.WARNING,
                frozenset({DeviceKind.CAMERA}),
                "clock_drift_s",
                Direction.ABOVE,
                raise_at=300,
                clear_at=60,
                label="desfase del reloj",
                unit=" s",
                confirm=2,
                window=3,
                clear_after=2,
            )
        ),
    )
