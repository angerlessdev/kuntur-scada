"""The schema the repositories query. Alembic migrations create it; a test checks they never drift apart.

Domain invariants are also enforced here, as a second line of defence: one active alert per device and
code (filtered unique index), a resolution time exactly when resolved, nothing resolved before raised.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Dialect,
    Float,
    ForeignKey,
    Identity,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Unicode,
    text,
)
from sqlalchemy.dialects import mssql
from sqlalchemy.types import TypeDecorator, TypeEngine

metadata = MetaData(
    naming_convention={
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }
)

TEXT_LIMIT = 400
"""Longest message or detail stored; longer driver details are cut, never rejected."""


class UtcDateTime(TypeDecorator[datetime]):
    """DATETIME2(6) holding UTC: exact round trip of a Python datetime. Aware values in, aware (UTC)
    values out. A naive datetime is a bug and is refused instead of being guessed.

    pymssql formats datetime parameters to the millisecond, so with it the value travels as ISO 8601
    text with microseconds; SQL Server converts that to DATETIME2 unambiguously, whatever the session's
    language, and the column keeps its type, so filters on it still use the indexes."""

    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "mssql":
            return dialect.type_descriptor(mssql.DATETIME2(precision=6))  # type: ignore[no-untyped-call]
        return dialect.type_descriptor(DateTime())

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | str | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Refusing a naive datetime: store timezone-aware values only")
        utc = value.astimezone(UTC).replace(tzinfo=None)
        return utc.isoformat(timespec="microseconds") if dialect.driver == "pymssql" else utc

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


devices = Table(
    "devices",
    metadata,
    Column("id", String(40), primary_key=True),
    Column("name", Unicode(120), nullable=False),
    Column("kind", String(16), nullable=False),
    Column("site", Unicode(120), nullable=False),
    Column("host", String(255), nullable=False),
    Column("port", Integer, nullable=False),
    Column("path", String(255), nullable=False),
    Column("installed_on", Date, nullable=False),
    Column("design_life_years", Float, nullable=False),
    Column("rated_cycles", BigInteger),
    Column("rated_impacts", Integer),
    Column("battery_design_life_years", Float),
    Column("active", Boolean, nullable=False),
    CheckConstraint("kind IN ('UPS', 'BARRIER', 'CAMERA')", name="kind"),
    CheckConstraint("port BETWEEN 1 AND 65535", name="port"),
)

readings = Table(
    "readings",
    metadata,
    Column("id", BigInteger, Identity(), nullable=False),
    Column("device_id", String(40), ForeignKey("devices.id"), nullable=False),
    Column("taken_at", UtcDateTime(), nullable=False),
    Column("status", String(8), nullable=False),
    Column("cause", String(24)),
    Column("detail", Unicode(TEXT_LIMIT)),
    Column("metrics", JSON, nullable=False),
    PrimaryKeyConstraint("id", mssql_clustered=False),
    CheckConstraint("status IN ('OK', 'PARTIAL', 'FAILED')", name="status"),
    CheckConstraint(
        "(status = 'OK' AND cause IS NULL) OR (status <> 'OK' AND cause IS NOT NULL)", name="cause"
    ),
    CheckConstraint("ISJSON(metrics) = 1", name="metrics_json"),
)
# Clustered by device and time: the latest reading and a device's history are index range scans
Index(
    "ix_readings_device_time", readings.c.device_id, readings.c.taken_at, readings.c.id, mssql_clustered=True
)

alerts = Table(
    "alerts",
    metadata,
    Column("id", String(32), nullable=False),
    Column("device_id", String(40), ForeignKey("devices.id"), nullable=False),
    Column("code", String(32), nullable=False),
    Column("severity", String(16), nullable=False),
    Column("message", Unicode(TEXT_LIMIT), nullable=False),
    Column("raised_at", UtcDateTime(), nullable=False),
    Column("state", String(16), nullable=False),
    Column("resolved_at", UtcDateTime()),
    PrimaryKeyConstraint("id", mssql_clustered=False),
    CheckConstraint("state IN ('ACTIVE', 'RESOLVED')", name="state"),
    CheckConstraint(
        "(state = 'ACTIVE' AND resolved_at IS NULL) OR (state = 'RESOLVED' AND resolved_at IS NOT NULL)",
        name="resolution",
    ),
    CheckConstraint("resolved_at IS NULL OR resolved_at >= raised_at", name="resolved_after_raised"),
)
Index("ix_alerts_raised_at", alerts.c.raised_at, alerts.c.id, mssql_clustered=True)
Index("ix_alerts_device_id_raised_at", alerts.c.device_id, alerts.c.raised_at)
Index(
    "ux_alerts_one_active",
    alerts.c.device_id,
    alerts.c.code,
    unique=True,
    mssql_where=text("state = 'ACTIVE'"),
)

commands = Table(
    "commands",
    metadata,
    Column("id", String(32), nullable=False),
    Column("device_id", String(40), ForeignKey("devices.id"), nullable=False),
    Column("kind", String(32), nullable=False),
    Column("requested_by", Unicode(120), nullable=False),
    Column("requested_at", UtcDateTime(), nullable=False),
    Column("status", String(16), nullable=False),
    Column("finished_at", UtcDateTime()),
    Column("detail", Unicode(TEXT_LIMIT)),
    PrimaryKeyConstraint("id", mssql_clustered=False),
    CheckConstraint("status IN ('PENDING', 'SUCCEEDED', 'FAILED')", name="status"),
    CheckConstraint(
        "(status = 'PENDING' AND finished_at IS NULL) OR (status <> 'PENDING' AND finished_at IS NOT NULL)",
        name="finish",
    ),
)
Index("ix_commands_requested_at", commands.c.requested_at, commands.c.id, mssql_clustered=True)
Index("ix_commands_device_id_requested_at", commands.c.device_id, commands.c.requested_at)
