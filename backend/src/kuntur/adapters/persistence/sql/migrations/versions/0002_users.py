"""Accounts: who can sign in and with which role.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("username", sa.String(40), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean, nullable=False),
        sa.PrimaryKeyConstraint("username", name="pk_users"),
        sa.CheckConstraint("role IN ('VIEWER', 'OPERATOR')", name="ck_users_role"),
    )


def downgrade() -> None:
    op.drop_table("users")
