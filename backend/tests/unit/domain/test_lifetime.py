from datetime import date, timedelta

import pytest

from kuntur.domain.errors import DomainValidationError
from kuntur.domain.lifetime import (
    ClockName,
    LifeClock,
    RemainingLife,
    battery_aging_factor,
    battery_clock,
    calendar_clock,
    mechanical_clock,
    miner_damage,
    remaining_life,
)
from tests.factories import barrier, camera, ups

TODAY = date(2026, 1, 15)


class TestClocks:
    def test_calendar_clock_after_half_the_design_life(self) -> None:
        clock = calendar_clock(age_days=int(5 * 365.25), design_life_years=10)
        assert clock.consumed == pytest.approx(0.5, abs=1e-3)
        assert clock.end_date(TODAY) == TODAY + timedelta(days=1827)

    def test_miner_damage_adds_the_fractions(self) -> None:
        # 2.5 M of 5 M cycles is 0.5; 500 of 2,000 impacts is 0.25
        assert miner_damage(2_500_000, 500, 5_000_000, 2_000) == pytest.approx(0.75)
        with pytest.raises(DomainValidationError):
            miner_damage(-1, 0, 10, 10)

    def test_mechanical_clock_projects_at_the_historical_pace(self) -> None:
        clock = mechanical_clock(2_500_000, 500, 5_000_000, 2_000, age_days=750)
        assert clock.daily_rate == pytest.approx(0.001)
        assert clock.end_date(TODAY) == TODAY + timedelta(days=250)

    def test_new_device_has_no_mechanical_pace(self) -> None:
        assert mechanical_clock(0, 0, 10, 10, age_days=0).end_date(TODAY) is None

    @pytest.mark.parametrize(("temp", "factor"), [(25, 1.0), (35, 2.0), (45, 4.0), (15, 0.5)])
    def test_battery_life_halves_every_ten_degrees(self, temp: float, factor: float) -> None:
        assert battery_aging_factor(temp) == pytest.approx(factor)

    def test_a_hot_battery_ends_sooner(self) -> None:
        cool = battery_clock(age_days=365, avg_temp_c=25, design_life_years=5)
        hot = battery_clock(age_days=365, avg_temp_c=35, design_life_years=5)
        assert hot.consumed == pytest.approx(2 * cool.consumed)
        assert hot.end_date(TODAY) < cool.end_date(TODAY)  # type: ignore[operator]

    def test_an_exhausted_clock_is_due_today(self) -> None:
        clock = LifeClock(ClockName.CALENDAR, consumed=1.2, daily_rate=0.001)
        assert clock.exhausted
        assert clock.remaining_fraction == 0
        assert clock.end_date(TODAY) == TODAY

    def test_projections_beyond_a_century_have_no_date(self) -> None:
        assert LifeClock(ClockName.CALENDAR, 0, 1e-9).end_date(TODAY) is None

    def test_negative_values_are_rejected(self) -> None:
        with pytest.raises(DomainValidationError):
            LifeClock(ClockName.CALENDAR, -0.1, 0)


class TestRemainingLife:
    def test_the_earliest_clock_governs(self) -> None:
        early = LifeClock(ClockName.BATTERY, 0.9, 0.01)
        late = LifeClock(ClockName.CALENDAR, 0.1, 0.0001)
        life = RemainingLife((late, early))
        assert life.governing(TODAY) is early
        assert life.replacement_date(TODAY) == TODAY + timedelta(days=10)

    def test_overdue_when_any_clock_is_exhausted(self) -> None:
        life = RemainingLife(
            (LifeClock(ClockName.CALENDAR, 1.0, 0.1), LifeClock(ClockName.BATTERY, 0.2, 0.0))
        )
        assert life.overdue(TODAY)

    def test_needs_a_clock(self) -> None:
        with pytest.raises(DomainValidationError):
            RemainingLife(())

    def test_barrier_gets_a_mechanical_clock_from_its_counters(self) -> None:
        life = remaining_life(barrier(), TODAY, {"cycles_total": 3_000_000, "impacts_total": 600})
        assert [c.name for c in life.clocks] == [ClockName.CALENDAR, ClockName.MECHANICAL]
        assert life.governing(TODAY).name is ClockName.MECHANICAL

    def test_ups_gets_a_battery_clock_from_the_temperature(self) -> None:
        life = remaining_life(ups(), TODAY, avg_battery_temp_c=38)
        assert [c.name for c in life.clocks] == [ClockName.CALENDAR, ClockName.BATTERY]
        assert life.governing(TODAY).name is ClockName.BATTERY

    def test_missing_data_drops_a_clock_instead_of_inventing_it(self) -> None:
        assert [c.name for c in remaining_life(barrier(), TODAY, {"cycles_total": 10}).clocks] == [
            ClockName.CALENDAR
        ]
        assert [c.name for c in remaining_life(ups(), TODAY).clocks] == [ClockName.CALENDAR]
        assert [c.name for c in remaining_life(camera(), TODAY).clocks] == [ClockName.CALENDAR]
