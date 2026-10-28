"""A real SQL Server 2022 for the tests: ``KUNTUR_TEST_DATABASE_URL`` if set (CI service, local
instance), otherwise a throwaway container. Without either, the SQL Server tests are skipped."""

from __future__ import annotations

import os
import secrets
from collections.abc import Iterator

import pytest
from sqlalchemy import Engine, delete
from sqlalchemy.engine import make_url

from kuntur.adapters.persistence.sql.database import create_sql_engine, ensure_database, upgrade
from kuntur.adapters.persistence.sql.schema import alerts, commands, devices, readings

IMAGE = "mcr.microsoft.com/mssql/server:2022-latest"
DATABASE = "kuntur_test"


@pytest.fixture(scope="session")
def sql_engine() -> Iterator[Engine]:
    url = os.environ.get("KUNTUR_TEST_DATABASE_URL")
    container = None
    if not url:
        try:
            from testcontainers.community.mssql import SqlServerContainer

            # SQL Server demands a complex password; a fresh one per run never leaves this process
            container = SqlServerContainer(IMAGE, password=f"{secrets.token_urlsafe(18)}aA1!")
            container.start()
        except Exception as exc:
            pytest.skip(f"SQL Server is not available: {exc}")
        url = container.get_connection_url()
    target = make_url(url).set(database=DATABASE)
    ensure_database(target)
    engine = create_sql_engine(target)
    upgrade(engine)
    try:
        yield engine
    finally:
        engine.dispose()
        if container is not None:
            container.stop()


@pytest.fixture
def clean_sql(sql_engine: Engine) -> Engine:
    with sql_engine.begin() as connection:
        for table in (readings, alerts, commands, devices):
            connection.execute(delete(table))
    return sql_engine
