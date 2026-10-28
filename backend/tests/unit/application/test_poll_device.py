import pytest

from kuntur.domain.health import Health
from kuntur.domain.readings import FailureCause, Reading, ReadingStatus
from tests.factories import T0, ok, ups
from tests.fakes import App, build_app


def _last(app: App) -> Reading:
    with app.uow() as uow:
        reading = uow.readings.latest("ups-01")
    assert reading is not None
    return reading


async def test_records_what_the_driver_read() -> None:
    app = build_app(ups())
    app.driver.readings.append(ok(0))
    assert await app.poll(ups()) is Health.OK
    assert _last(app) == ok(0)


async def test_a_driver_that_hangs_becomes_a_timeout() -> None:
    app = build_app(ups(), timeout_s=0.05)
    app.driver.readings.append(ok(0))
    app.driver.delay_s = 1.0
    assert await app.poll(ups()) is Health.DEGRADED
    reading = _last(app)
    assert (reading.status, reading.cause, reading.detail) == (
        ReadingStatus.FAILED,
        FailureCause.TIMEOUT,
        "Sin respuesta en 0.05 s",
    )
    assert reading.taken_at == T0


async def test_a_driver_that_crashes_is_recorded_not_propagated(caplog: pytest.LogCaptureFixture) -> None:
    app = build_app(ups())
    app.driver.readings.append(ValueError("bug"))
    assert await app.poll(ups()) is Health.DEGRADED
    reading = _last(app)
    assert (reading.cause, reading.detail) == (FailureCause.UNKNOWN, "ValueError")
    assert "crashed" in caplog.text
