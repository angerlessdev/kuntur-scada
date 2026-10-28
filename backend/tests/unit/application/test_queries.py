from datetime import date

import pytest

from kuntur.domain.alerts import AlertState
from kuntur.domain.errors import NotFoundError
from kuntur.domain.health import Health
from kuntur.domain.lifetime import ClockName
from tests.factories import at, barrier, camera, failed, ok, ups
from tests.fakes import build_app


def test_a_device_never_read_is_grey_and_ages_by_the_calendar() -> None:
    app = build_app(camera())
    view = app.queries.device("camara-01")
    assert view.health is Health.UNKNOWN
    assert view.last_reading is None
    assert [clock.name for clock in view.life.clocks] == [ClockName.CALENDAR]
    # Seven years after being installed on 2024-03-01, give or take the leap days
    assert view.replacement_date is not None
    assert abs((view.replacement_date - date(2031, 3, 1)).days) <= 1


def test_a_hot_battery_brings_the_replacement_forward() -> None:
    def replacement_at(temp_c: float) -> date:
        app = build_app(ups())
        for i in range(3):
            app.record(ok(i, battery_temp_c=temp_c))
        view = app.queries.device("ups-01")
        assert view.life.governing(view.today).name is ClockName.BATTERY
        assert view.replacement_date is not None
        return view.replacement_date

    assert replacement_at(33.0) < replacement_at(29.0) < replacement_at(25.0)


def test_mechanical_wear_uses_the_last_reading_that_answered() -> None:
    app = build_app(barrier())
    app.record(ok(0, "barrera-01", cycles_total=4_000_000, impacts_total=100))
    app.record(failed(1, "barrera-01"))
    view = app.queries.device("barrera-01")
    assert view.health is Health.DEGRADED
    assert view.last_reading == failed(1, "barrera-01")
    assert view.life.governing(view.today).name is ClockName.MECHANICAL


def test_the_overview_leaves_out_devices_out_of_service() -> None:
    app = build_app(ups(), camera(), ups("ups-02", active=False))
    assert [view.device.id for view in app.queries.overview()] == ["camara-01", "ups-01"]


def test_readings_are_the_latest_or_a_window() -> None:
    app = build_app(ups())
    for i in range(5):
        app.record(ok(i))
    assert [r.taken_at for r in app.queries.readings("ups-01", None, 2)] == [at(3), at(4)]
    assert [r.taken_at for r in app.queries.readings("ups-01", at(2), 2)] == [at(2), at(3)]


def test_readings_of_an_unknown_device_are_not_found() -> None:
    with pytest.raises(NotFoundError):
        build_app().queries.readings("fantasma", None, 10)


def test_an_alert_is_found_by_its_id() -> None:
    app = build_app(ups())
    for i in range(4):
        app.record(failed(i))
    [alert] = app.queries.alerts(state=AlertState.ACTIVE, device_id=None, limit=10)
    assert app.queries.alert(alert.id) == alert
    with pytest.raises(NotFoundError):
        app.queries.alert("no-existe")
