import asyncio
from datetime import datetime

import pytest

from kuntur.application.acquisition import PollDevice, RecordReading
from kuntur.application.collector import Collector
from kuntur.domain.commands import CommandKind
from kuntur.domain.devices import Device
from kuntur.domain.health import Health
from kuntur.domain.readings import Reading
from tests.factories import barrier, camera, ups
from tests.fakes import App, SingleDriverRegistry, build_app


class CountingDriver:
    """Answers every device and records how many reads were in flight at once."""

    def __init__(self, delay_s: float = 0.02) -> None:
        self.delay_s = delay_s
        self.in_flight = 0
        self.peak = 0
        self.read_ids: list[str] = []

    async def read(self, device: Device, at: datetime) -> Reading:
        self.in_flight += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            await asyncio.sleep(self.delay_s)
            self.read_ids.append(device.id)
            return Reading.ok(device.id, at, {"x": 1.0})
        finally:
            self.in_flight -= 1

    async def execute(self, device: Device, command: CommandKind) -> str:
        return "Ejecutado"


class FailingRecord(RecordReading):
    """Stores every reading except those of ``ups-01``, as if the database rejected them."""

    def __call__(self, reading: Reading, *, elapsed_s: float | None = None) -> Health:
        if reading.device_id == "ups-01":
            raise RuntimeError("base de datos caída")
        return super().__call__(reading, elapsed_s=elapsed_s)


def _collector(
    app: App,
    driver: CountingDriver,
    record: RecordReading | None = None,
    *,
    interval_s: float = 5.0,
    max_concurrency: int = 16,
) -> Collector:
    poll = PollDevice(SingleDriverRegistry(driver), record or app.record, app.clock, 1.0)
    return Collector(poll, app.uow, interval_s=interval_s, max_concurrency=max_concurrency)


async def test_one_round_polls_every_active_device() -> None:
    driver = CountingDriver()
    collector = _collector(build_app(ups(), camera(), ups("ups-02", active=False)), driver)
    assert await collector.run_once() == 2
    assert sorted(driver.read_ids) == ["camara-01", "ups-01"]


async def test_concurrency_is_bounded() -> None:
    driver = CountingDriver()
    collector = _collector(build_app(*[ups(f"ups-{i:02}") for i in range(10)]), driver, max_concurrency=3)
    await collector.run_once()
    assert (len(driver.read_ids), driver.peak) == (10, 3)


async def test_a_reading_that_cannot_be_stored_does_not_stop_the_round(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = build_app(ups(), barrier())
    failing = FailingRecord(app.record.uow_factory, app.record.engine, app.record.publisher, app.record.ids)
    assert await _collector(app, CountingDriver(), failing).run_once() == 2
    with app.uow() as uow:
        assert uow.readings.latest("barrera-01") is not None
    assert "Could not poll or record ups-01" in caplog.text


async def test_it_keeps_the_cadence_until_told_to_stop() -> None:
    driver = CountingDriver(delay_s=0)
    collector = _collector(build_app(ups()), driver, interval_s=0.05)
    stop = asyncio.Event()
    task = asyncio.create_task(collector.run_forever(stop))
    await asyncio.sleep(0.18)
    stop.set()
    await asyncio.wait_for(task, 1)
    assert 2 <= len(driver.read_ids) <= 5
