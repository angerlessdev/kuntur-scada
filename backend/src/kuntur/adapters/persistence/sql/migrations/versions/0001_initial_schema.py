"""Initial schema: devices, readings, alerts and the command audit log.

Revision ID: 0001
Revises:
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mssql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UTC_TIME = mssql.DATETIME2(precision=6)


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.String(40), nullable=False),
        sa.Column("name", sa.Unicode(120), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("site", sa.Unicode(120), nullable=False),
        sa.Column("host", sa.String(255), nullable=False),
        sa.Column("port", sa.Integer, nullable=False),
        sa.Column("path", sa.String(255), nullable=False),
        sa.Column("installed_on", sa.Date, nullable=False),
        sa.Column("design_life_years", sa.Float, nullable=False),
        sa.Column("rated_cycles", sa.BigInteger),
        sa.Column("rated_impacts", sa.Integer),
        sa.Column("battery_design_life_years", sa.Float),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_devices"),
        sa.CheckConstraint("kind IN ('UPS', 'BARRIER', 'CAMERA')", name="ck_devices_kind"),
        sa.CheckConstraint("port BETWEEN 1 AND 65535", name="ck_devices_port"),
    )

    op.create_table(
        "readings",
        sa.Column("id", sa.BigInteger, sa.Identity(), nullable=False),
        sa.Column("device_id", sa.String(40), nullable=False),
        sa.Column("taken_at", UTC_TIME, nullable=False),
        sa.Column("status", sa.String(8), nullable=False),
        sa.Column("cause", sa.String(24)),
        sa.Column("detail", sa.Unicode(400)),
        sa.Column("metrics", sa.JSON, nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_readings", mssql_clustered=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], name="fk_readings_device_id_devices"),
        sa.CheckConstraint("status IN ('OK', 'PARTIAL', 'FAILED')", name="ck_readings_status"),
        sa.CheckConstraint(
            "(status = 'OK' AND cause IS NULL) OR (status <> 'OK' AND cause IS NOT NULL)",
            name="ck_readings_cause",
        ),
        sa.CheckConstraint("ISJSON(metrics) = 1", name="ck_readings_metrics_json"),
    )
    op.create_index(
        "ix_readings_device_time", "readings", ["device_id", "taken_at", "id"], mssql_clustered=True
    )

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("device_id", sa.String(40), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("severity", sa.String(16), nullable=False),
        sa.Column("message", sa.Unicode(400), nullable=False),
        sa.Column("raised_at", UTC_TIME, nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("resolved_at", UTC_TIME),
        sa.PrimaryKeyConstraint("id", name="pk_alerts", mssql_clustered=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], name="fk_alerts_device_id_devices"),
        sa.CheckConstraint("state IN ('ACTIVE', 'RESOLVED')", name="ck_alerts_state"),
        sa.CheckConstraint(
            "(state = 'ACTIVE' AND resolved_at IS NULL) OR (state = 'RESOLVED' AND resolved_at IS NOT NULL)",
            name="ck_alerts_resolution",
        ),
        sa.CheckConstraint(
            "resolved_at IS NULL OR resolved_at >= raised_at", name="ck_alerts_resolved_after_raised"
        ),
    )
    op.create_index("ix_alerts_raised_at", "alerts", ["raised_at", "id"], mssql_clustered=True)
    op.create_index("ix_alerts_device_id_raised_at", "alerts", ["device_id", "raised_at"])
    op.create_index(
        "ux_alerts_one_active",
        "alerts",
        ["device_id", "code"],
        unique=True,
        mssql_where=sa.text("state = 'ACTIVE'"),
    )

    op.create_table(
        "commands",
        sa.Column("id", sa.String(32), nullable=False),
        sa.Column("device_id", sa.String(40), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("requested_by", sa.Unicode(120), nullable=False),
        sa.Column("requested_at", UTC_TIME, nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("finished_at", UTC_TIME),
        sa.Column("detail", sa.Unicode(400)),
        sa.PrimaryKeyConstraint("id", name="pk_commands", mssql_clustered=False),
        sa.ForeignKeyConstraint(["device_id"], ["devices.id"], name="fk_commands_device_id_devices"),
        sa.CheckConstraint("status IN ('PENDING', 'SUCCEEDED', 'FAILED')", name="ck_commands_status"),
        sa.CheckConstraint(
            "(status = 'PENDING' AND finished_at IS NULL)"
            " OR (status <> 'PENDING' AND finished_at IS NOT NULL)",
            name="ck_commands_finish",
        ),
    )
    op.create_index("ix_commands_requested_at", "commands", ["requested_at", "id"], mssql_clustered=True)
    op.create_index("ix_commands_device_id_requested_at", "commands", ["device_id", "requested_at"])


def downgrade() -> None:
    for table in ("commands", "alerts", "readings", "devices"):
        op.drop_table(table)
