from concurrent.futures import ThreadPoolExecutor

from kuntur.adapters.persistence.memory import InMemoryStore, InMemoryUnitOfWork
from kuntur.domain.devices import Device
from tests.factories import at, failed, ok, ups
from tests.fakes import build_app


def _committed_device(store: InMemoryStore) -> Device | None:
    with InMemoryUnitOfWork(store) as uow:
        return uow.devices.get("ups-01")


def test_leaving_without_commit_discards_everything() -> None:
    store = InMemoryStore()
    with InMemoryUnitOfWork(store) as uow:
        uow.devices.add(ups())
        uow.readings.add(ok(0))
    assert _committed_device(store) is None
    assert store.readings == {}


def test_rollback_discards_and_the_transaction_goes_on() -> None:
    store = InMemoryStore()
    with InMemoryUnitOfWork(store) as uow:
        uow.devices.add(ups())
        uow.rollback()
        assert uow.devices.get("ups-01") is None
        uow.devices.add(ups())
        uow.commit()
    assert _committed_device(store) == ups()


def test_a_transaction_reads_its_own_pending_writes() -> None:
    store = InMemoryStore()
    with InMemoryUnitOfWork(store) as uow:
        uow.readings.add(ok(0))
        uow.readings.add(failed(1))
        assert uow.readings.recent("ups-01", 5) == [ok(0), failed(1)]
        assert uow.readings.latest("ups-01") == failed(1)
        assert uow.readings.latest("ups-01", answered_only=True) == ok(0)


def test_entities_handed_out_are_copies() -> None:
    store = InMemoryStore()
    with InMemoryUnitOfWork(store) as uow:
        uow.devices.add(ups())
        uow.commit()
        device = uow.devices.get("ups-01")
        assert device is not None
        device.name = "cambiado sin update()"
        uow.commit()
    committed = _committed_device(store)
    assert committed is not None
    assert committed.name == ups().name


def test_history_is_capped_per_device() -> None:
    store = InMemoryStore(max_readings_per_device=3)
    with InMemoryUnitOfWork(store) as uow:
        for i in range(5):
            uow.readings.add(ok(i))
        uow.commit()
        assert [r.taken_at for r in uow.readings.recent("ups-01", 10)] == [at(2), at(3), at(4)]


def test_average_skips_readings_without_the_metric() -> None:
    store = InMemoryStore()
    with InMemoryUnitOfWork(store) as uow:
        for i, temp in enumerate([30.0, 34.0]):
            uow.readings.add(ok(i, battery_temp_c=temp))
        uow.readings.add(failed(2))
        assert uow.readings.average("ups-01", "battery_temp_c", at(0)) == 32.0
        assert uow.readings.average("ups-01", "battery_temp_c", at(2)) is None


def test_concurrent_writers_lose_nothing() -> None:
    app = build_app(ups(), rules=[])

    def write(start: int) -> None:
        for i in range(start, start + 50):
            app.record(ok(i))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(write, range(0, 400, 50)))
    with app.uow() as uow:
        assert len(uow.readings.recent("ups-01", 1000)) == 400
