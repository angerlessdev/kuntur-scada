"""Remaining useful life: every wear mode is a clock, and the earliest one sets the replacement date.

* **Calendar:** ageing by time in service against the design life.
* **Mechanical (barriers):** Palmgren-Miner cumulative damage, ``D = cycles / N_cycles + impacts /
  N_impacts``. The mechanism is spent when ``D`` reaches 1.
* **Battery (UPS):** calendar ageing accelerated by temperature. The usual Arrhenius rule of thumb for
  lead-acid batteries: every 10 °C above 25 °C halves the life.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

from kuntur.domain.devices import Device, DeviceKind
from kuntur.domain.errors import DomainValidationError

DAYS_PER_YEAR = 365.25
MAX_HORIZON_DAYS = int(100 * DAYS_PER_YEAR)
"""Projections beyond a century are reported as 'no foreseeable end'."""


class ClockName(StrEnum):
    CALENDAR = "CALENDAR"
    MECHANICAL = "MECHANICAL"
    BATTERY = "BATTERY"


@dataclass(frozen=True, slots=True)
class LifeClock:
    """``consumed`` is the fraction of life used (it can exceed 1); ``daily_rate`` the fraction used
    per day at the current pace."""

    name: ClockName
    consumed: float
    daily_rate: float

    def __post_init__(self) -> None:
        if self.consumed < 0 or self.daily_rate < 0:
            raise DomainValidationError("Life consumption cannot be negative")

    @property
    def remaining_fraction(self) -> float:
        return max(0.0, 1.0 - self.consumed)

    @property
    def exhausted(self) -> bool:
        return self.consumed >= 1.0

    def end_date(self, today: date) -> date | None:
        """When the clock reaches 100 %, or ``None`` if it never will at this pace."""
        if self.exhausted:
            return today
        if self.daily_rate == 0:
            return None
        days = math.ceil((1.0 - self.consumed) / self.daily_rate)
        return None if days > MAX_HORIZON_DAYS else today + timedelta(days=days)


@dataclass(frozen=True, slots=True)
class RemainingLife:
    clocks: tuple[LifeClock, ...]

    def __post_init__(self) -> None:
        if not self.clocks:
            raise DomainValidationError("Remaining life needs at least one clock")

    def governing(self, today: date) -> LifeClock:
        """The clock that runs out first; on equal dates, the most consumed one."""

        def key(clock: LifeClock) -> tuple[date, float]:
            return clock.end_date(today) or date.max, -clock.consumed

        return min(self.clocks, key=key)

    def replacement_date(self, today: date) -> date | None:
        return self.governing(today).end_date(today)

    def overdue(self, today: date) -> bool:
        return any(clock.exhausted for clock in self.clocks)


def calendar_clock(age_days: int, design_life_years: float) -> LifeClock:
    life_days = design_life_years * DAYS_PER_YEAR
    return LifeClock(ClockName.CALENDAR, age_days / life_days, 1.0 / life_days)


def miner_damage(cycles: float, impacts: float, rated_cycles: int, rated_impacts: int) -> float:
    if cycles < 0 or impacts < 0:
        raise DomainValidationError("Counters cannot be negative")
    return cycles / rated_cycles + impacts / rated_impacts


def mechanical_clock(
    cycles: float, impacts: float, rated_cycles: int, rated_impacts: int, age_days: int
) -> LifeClock:
    damage = miner_damage(cycles, impacts, rated_cycles, rated_impacts)
    rate = damage / age_days if age_days > 0 else 0.0
    return LifeClock(ClockName.MECHANICAL, damage, rate)


def battery_aging_factor(temp_c: float, reference_c: float = 25.0, halving_step_c: float = 10.0) -> float:
    """How many times faster than at ``reference_c`` the battery ages (1.0 at 25 °C, 2.0 at 35 °C)."""
    return float(2.0 ** ((temp_c - reference_c) / halving_step_c))


def battery_clock(age_days: int, avg_temp_c: float, design_life_years: float) -> LifeClock:
    factor = battery_aging_factor(avg_temp_c)
    life_days = design_life_years * DAYS_PER_YEAR
    return LifeClock(ClockName.BATTERY, age_days * factor / life_days, factor / life_days)


def remaining_life(
    device: Device,
    today: date,
    latest_metrics: Mapping[str, float] | None = None,
    avg_battery_temp_c: float | None = None,
) -> RemainingLife:
    """Builds every clock the available data supports. Missing data drops a clock, never invents it."""
    age = device.age_in_days(today)
    clocks = [calendar_clock(age, device.lifetime.design_life_years)]
    metrics = latest_metrics or {}
    profile = device.lifetime

    if device.kind is DeviceKind.BARRIER and profile.rated_cycles and profile.rated_impacts:
        cycles, impacts = metrics.get("cycles_total"), metrics.get("impacts_total")
        if cycles is not None and impacts is not None:
            clocks.append(mechanical_clock(cycles, impacts, profile.rated_cycles, profile.rated_impacts, age))

    if device.kind is DeviceKind.UPS and profile.battery_design_life_years and avg_battery_temp_c is not None:
        clocks.append(battery_clock(age, avg_battery_temp_c, profile.battery_design_life_years))

    return RemainingLife(tuple(clocks))
