"""One contract, two implementations: the in-memory unit of work used by the fast tests must behave
exactly like SQL Server, or those tests would be proving the wrong thing."""

from dataclasses import replace
from datetime import timedelta

import pytest

from kuntur.adapters.persistence.memory import InMemoryStore, InMemoryUnitOfWork
from kuntur.adapters.persistence.sql.unit_of_work import SqlUnitOfWork
from kuntur.application.ports import UnitOfWork, UnitOfWorkFactory
from kuntur.domain.alerts import Alert, AlertCode, AlertState, Severity
from kuntur.domain.commands import Command, CommandKind
from kuntur.domain.devices import Device
from kuntur.domain.readings import FailureCause, Reading
from tests.factories import T0, at, barrier, camera, ups


@pytest.fixture(params=["memory", pytest.param("sqlserver", marks=pytest.mark.integration)])
def uow_factory(request: pytest.FixtureRequest) -> UnitOfWorkFactory:
    if request.param == "memory":
        store = InMemoryStore()

        def memory() -> UnitOfWork:
            return InMemoryUnitOfWork(store)

        return memory
    engine = request.getfixturevalue("clean_sql")

    def sql() -> UnitOfWork:
        return SqlUnitOfWork(engine)

    return sql


def seed(factory: UnitOfWorkFactory, *devices: Device) -> None:
    with factory() as uow:
        for device in devices:
            uow.devices.add(device)
        uow.commit()


def alert(index: int, code: AlertCode = AlertCode.DEVICE_UNREACHABLE, device_id: str = "ups-01") -> Alert:
    return Alert(f"alerta-{index}", device_id, code, Severity.CRITICAL, "Sin comunicación", at(index))


class TestDevices:
    def test_add_get_list_and_update(self, uow_factory: UnitOfWorkFactory) -> None:
        seed(uow_factory, ups(), camera(), barrier(), ups("ups-02", active=False))
        with uow_factory() as uow:
            assert uow.devices.get("ups-01") == ups()
            assert uow.devices.get("barrera-01") == barrier()
            assert uow.devices.get("nadie") is None
            assert [d.id for d in uow.devices.list()] == ["barrera-01", "camara-01", "ups-01", "ups-02"]
            assert [d.id for d in uow.devices.list(active_only=True)] == ["barrera-01", "camara-01", "ups-01"]
            uow.devices.update(ups(name="UPS renovado"))
            uow.commit()
        with uow_factory() as uow:
            assert uow.devices.get("ups-01") == ups(name="UPS renovado")

    def test_a_device_is_added_only_once(self, uow_factory: UnitOfWorkFactory) -> None:
        seed(uow_factory, ups())
        with uow_factory() as uow, pytest.raises(ValueError, match="already exists"):
            uow.devices.add(ups())

    def test_updating_an_unknown_device_fails(self, uow_factory: UnitOfWorkFactory) -> None:
        with uow_factory() as uow, pytest.raises(KeyError):
            uow.devices.update(ups())


class TestReadings:
    STORED = (
        Reading.ok(
            "ups-01", T0 + timedelta(microseconds=123_456), {"load_pct": 41.2, "battery_temp_c": -5.5}
        ),
        Reading.partial("ups-01", at(1), {"load_pct": 40.0}, FailureCause.INVALID_DATA, "Sensor sin dato"),
        Reading.failed("ups-01", at(2), FailureCause.TIMEOUT, "El equipo no respondió a tiempo"),
    )

    def test_the_round_trip_keeps_microseconds_metrics_and_causes(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        seed(uow_factory, ups())
        with uow_factory() as uow:
            for reading in self.STORED:
                uow.readings.add(reading)
            uow.commit()
        with uow_factory() as uow:
            assert uow.readings.recent("ups-01", 10) == list(self.STORED)
            assert uow.readings.recent("ups-01", 2) == list(self.STORED[1:])
            assert uow.readings.recent("ups-01", 0) == []

    def test_latest_and_history(self, uow_factory: UnitOfWorkFactory) -> None:
        seed(uow_factory, ups())
        with uow_factory() as uow:
            for reading in self.STORED:
                uow.readings.add(reading)
            uow.commit()
            assert uow.readings.latest("ups-01") == self.STORED[2]
            assert uow.readings.latest("ups-01", answered_only=True) == self.STORED[1]
            assert uow.readings.latest("otro") is None
            assert uow.readings.history("ups-01", at(1), 10) == list(self.STORED[1:])
            assert uow.readings.history("ups-01", T0, 1) == [self.STORED[0]]

    def test_the_average_skips_readings_without_the_metric(self, uow_factory: UnitOfWorkFactory) -> None:
        seed(uow_factory, ups())
        with uow_factory() as uow:
            uow.readings.add(Reading.ok("ups-01", at(0), {"battery_temp_c": 30.0}))
            uow.readings.add(Reading.ok("ups-01", at(1), {"battery_temp_c": 34.0}))
            uow.readings.add(Reading.failed("ups-01", at(2), FailureCause.TIMEOUT))
            uow.commit()
            assert uow.readings.average("ups-01", "battery_temp_c", at(0)) == pytest.approx(32.0)
            assert uow.readings.average("ups-01", "battery_temp_c", at(1)) == pytest.approx(34.0)
            assert uow.readings.average("ups-01", "battery_temp_c", at(2)) is None


class TestAlerts:
    def test_active_search_and_resolution(self, uow_factory: UnitOfWorkFactory) -> None:
        seed(uow_factory, ups(), camera())
        first, second, other = alert(1), alert(2, AlertCode.UPS_BATTERY_HOT), alert(3, device_id="camara-01")
        with uow_factory() as uow:
            for item in (first, second, other):
                uow.alerts.add(item)
            uow.commit()
            assert uow.alerts.active("ups-01") == [first, second]
            assert uow.alerts.active() == [first, second, other]
            first.resolve(at(5))
            uow.alerts.update(first)
            uow.commit()
        with uow_factory() as uow:
            assert uow.alerts.get(first.id) == first
            assert uow.alerts.get("no-existe") is None
            assert uow.alerts.search(state=AlertState.RESOLVED, device_id=None, limit=10) == [first]
            assert [a.id for a in uow.alerts.search(state=None, device_id=None, limit=2)] == [
                other.id,
                second.id,
            ]
            assert uow.alerts.search(state=AlertState.ACTIVE, device_id="ups-01", limit=10) == [second]

    def test_the_last_resolution_per_code(self, uow_factory: UnitOfWorkFactory) -> None:
        seed(uow_factory, ups())
        old, new = alert(1), alert(10)
        old.resolve(at(4))
        new.resolve(at(12))
        with uow_factory() as uow:
            uow.alerts.add(old)
            uow.alerts.add(new)
            uow.commit()
            assert uow.alerts.last_resolved_at("ups-01") == {AlertCode.DEVICE_UNREACHABLE: at(12)}
            assert uow.alerts.last_resolved_at("otro") == {}

    def test_updating_an_unknown_alert_fails(self, uow_factory: UnitOfWorkFactory) -> None:
        with uow_factory() as uow, pytest.raises(KeyError):
            uow.alerts.update(alert(1))


class TestCommands:
    def test_the_audit_log_is_newest_first_and_records_the_outcome(
        self, uow_factory: UnitOfWorkFactory
    ) -> None:
        seed(uow_factory, barrier(), ups())
        opened = Command("orden-1", "barrera-01", CommandKind.BARRIER_OPEN, "operador", at(1))
        tested = Command("orden-2", "ups-01", CommandKind.UPS_BATTERY_TEST, "operador", at(2))
        with uow_factory() as uow:
            uow.commands.add(opened)
            uow.commands.add(tested)
            opened.succeed(at(1), "Barrera abierta")
            uow.commands.update(opened)
            uow.commit()
        with uow_factory() as uow:
            assert uow.commands.search(device_id=None, limit=10) == [tested, opened]
            assert uow.commands.search(device_id="barrera-01", limit=10) == [opened]
            with pytest.raises(KeyError):
                uow.commands.update(replace(tested, id="no-existe"))


class TestTransactions:
    def test_leaving_without_commit_undoes_everything(self, uow_factory: UnitOfWorkFactory) -> None:
        with uow_factory() as uow:
            uow.devices.add(ups())
        with uow_factory() as uow:
            assert uow.devices.get("ups-01") is None

    def test_another_transaction_never_sees_uncommitted_work(self, uow_factory: UnitOfWorkFactory) -> None:
        with uow_factory() as writer:
            writer.devices.add(ups())
            with uow_factory() as reader:  # on SQL Server this would block without READ_COMMITTED_SNAPSHOT
                assert reader.devices.get("ups-01") is None

    def test_rollback_discards_and_the_unit_of_work_goes_on(self, uow_factory: UnitOfWorkFactory) -> None:
        with uow_factory() as uow:
            uow.devices.add(ups())
            uow.rollback()
            assert uow.devices.get("ups-01") is None
            uow.devices.add(ups())
            uow.commit()
        with uow_factory() as uow:
            assert uow.devices.get("ups-01") == ups()
