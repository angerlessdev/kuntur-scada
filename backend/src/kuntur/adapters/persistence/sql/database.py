"""Engine, database bootstrap and migrations."""

from __future__ import annotations

import re

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import URL, make_url

_DATABASE_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")


def create_sql_engine(url: str | URL, *, pool_size: int = 5) -> Engine:
    return create_engine(
        url,
        pool_size=pool_size,
        max_overflow=pool_size,
        pool_pre_ping=True,
        connect_args={"login_timeout": 10, "timeout": 30, "appname": "kuntur"},
    )


def ensure_database(url: str | URL) -> bool:
    """Creates the database named in ``url`` if it does not exist, with READ_COMMITTED_SNAPSHOT so the
    screens' reads never block the collector's writes. Returns whether it had to create it."""
    target = make_url(url)
    name = target.database or ""
    if not _DATABASE_NAME.fullmatch(name):
        raise ValueError(f"Refusing an unusual database name: {name!r}")
    server = create_sql_engine(target.set(database="master"), pool_size=1).execution_options(
        isolation_level="AUTOCOMMIT"
    )
    try:
        with server.connect() as connection:
            if connection.execute(text("SELECT DB_ID(:name)"), {"name": name}).scalar() is not None:
                return False
            # The name was validated above: identifiers cannot be bound as parameters
            connection.execute(text(f"CREATE DATABASE [{name}]"))
            connection.execute(text(f"ALTER DATABASE [{name}] SET READ_COMMITTED_SNAPSHOT ON"))
            return True
    finally:
        server.dispose()


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", "kuntur.adapters.persistence.sql:migrations")
    return config


def upgrade(engine: Engine, revision: str = "head") -> None:
    config = alembic_config()
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, revision)
