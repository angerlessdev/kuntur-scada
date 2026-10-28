"""What only SQL Server can prove: the migrations, the constraints behind the domain, a full use case."""

from datetime import datetime

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Engine, insert
from sqlalchemy.exc import IntegrityError, StatementError

from kuntur.adapters.events import InMemoryEventBus
from kuntur.adapters.persistence.sql.schema import alerts, metadata, readings
from kuntur.adapters.persistence.sql.unit_of_work import SqlUnitOfWork
from kuntur.application.acquisition import RecordReading
from kuntur.application.fleet import sync_fleet
from kuntur.application.ports import UnitOfWork
from kuntur.domain.alerts import AlertCode, AlertState
from kuntur.domain.health import Health
from kuntur.domain.rules import AlertEngine, default_rules
from tests.factories import at, failed, ups
from tests.fakes import SequentialIds

pytestmark = pytest.mark.integration


def test_the_migrations_build_exactly_the_schema_the_code_queries(sql_engine: Engine) -> None:
    with sql_engine.connect() as connection:
        context = MigrationContext.configure(connection, opts={"compare_type": True})
        assert compare_metadata(context, metadata) == []


def _alert_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "id": "a1",
        "device_id": "ups-01",
        "code": AlertCode.DEVICE_UNREACHABLE.value,
        "severity": "CRITICAL",
        "message": "Sin comunicación",
        "raised_at": at(1),
        "state": AlertState.ACTIVE.value,
        "resolved_at": None,
    }
    return {**row, **overrides}


def _with_device(engine: Engine) -> None:
    def factory() -> UnitOfWork:
        return SqlUnitOfWork(engine)

    sync_fleet(factory, [ups()])


def test_the_database_refuses_a_second_active_alert_for_the_same_code(clean_sql: Engine) -> None:
    _with_device(clean_sql)
    with clean_sql.begin() as connection:
        connection.execute(insert(alerts).values(_alert_row()))
        connection.execute(insert(alerts).values(_alert_row(id="a2", state="RESOLVED", resolved_at=at(2))))
    with pytest.raises(IntegrityError), clean_sql.begin() as connection:
        connection.execute(insert(alerts).values(_alert_row(id="a3")))


@pytest.mark.parametrize(
    "bad",
    [
        {"state": "RESOLVED", "resolved_at": None},
        {"state": "ACTIVE", "resolved_at": at(2)},
        {"state": "RESOLVED", "resolved_at": at(0)},
    ],
    ids=["resolved-without-time", "active-with-time", "resolved-before-raised"],
)
def test_the_database_refuses_an_inconsistent_resolution(clean_sql: Engine, bad: dict[str, object]) -> None:
    _with_device(clean_sql)
    with pytest.raises(IntegrityError), clean_sql.begin() as connection:
        connection.execute(insert(alerts).values(_alert_row(**bad)))


def test_a_naive_datetime_never_reaches_the_database(clean_sql: Engine) -> None:
    _with_device(clean_sql)
    row = {"device_id": "ups-01", "taken_at": datetime(2026, 1, 15, 8, 0), "status": "OK", "metrics": {}}  # noqa: DTZ001
    with pytest.raises(StatementError, match="naive"), clean_sql.begin() as connection:
        connection.execute(insert(readings).values(row))


def test_a_confirmed_loss_of_contact_end_to_end(clean_sql: Engine) -> None:
    def factory() -> UnitOfWork:
        return SqlUnitOfWork(clean_sql)

    sync_fleet(factory, [ups()])
    record = RecordReading(factory, AlertEngine(default_rules()), InMemoryEventBus(), SequentialIds())
    healths = [record(failed(i)) for i in range(5)]
    assert healths[-1] is Health.DOWN
    with factory() as uow:
        [alert] = uow.alerts.active("ups-01")
        assert alert.code is AlertCode.DEVICE_UNREACHABLE
        assert len(uow.readings.recent("ups-01", 100)) == 5
