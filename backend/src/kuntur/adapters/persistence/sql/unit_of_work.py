"""One business transaction on SQL Server: one connection, one transaction, four repositories."""

from __future__ import annotations

from types import TracebackType
from typing import Self

from sqlalchemy import Connection, Engine, RootTransaction

from kuntur.adapters.persistence.sql.repositories import (
    SqlAlertRepository,
    SqlCommandRepository,
    SqlDeviceRepository,
    SqlReadingRepository,
    SqlUserRepository,
)
from kuntur.application.ports import (
    AlertRepository,
    CommandRepository,
    DeviceRepository,
    ReadingRepository,
    UserRepository,
)


class SqlUnitOfWork:
    devices: DeviceRepository
    readings: ReadingRepository
    alerts: AlertRepository
    commands: CommandRepository
    users: UserRepository

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._connection: Connection | None = None
        self._transaction: RootTransaction | None = None

    def __enter__(self) -> Self:
        self._connection = self._engine.connect()
        self._transaction = self._connection.begin()
        self.devices = SqlDeviceRepository(self._connection)
        self.readings = SqlReadingRepository(self._connection)
        self.alerts = SqlAlertRepository(self._connection)
        self.commands = SqlCommandRepository(self._connection)
        self.users = SqlUserRepository(self._connection)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        connection, transaction = self._connection, self._transaction
        self._connection = self._transaction = None
        if connection is None:
            return
        try:
            if transaction is not None and transaction.is_active:
                transaction.rollback()  # whatever was not committed is undone
        finally:
            connection.close()

    def _active(self) -> tuple[Connection, RootTransaction]:
        if self._connection is None or self._transaction is None:
            raise RuntimeError("Use the unit of work inside a 'with' block")
        return self._connection, self._transaction

    def commit(self) -> None:
        connection, transaction = self._active()
        transaction.commit()
        self._transaction = connection.begin()

    def rollback(self) -> None:
        connection, transaction = self._active()
        transaction.rollback()
        self._transaction = connection.begin()
