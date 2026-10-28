"""Alembic environment. Migrations run through ``database.upgrade()``, which hands over the connection."""

from alembic import context

from kuntur.adapters.persistence.sql.schema import metadata

connection = context.config.attributes.get("connection")
if connection is None:
    raise RuntimeError("Run migrations with kuntur.adapters.persistence.sql.database.upgrade()")

context.configure(connection=connection, target_metadata=metadata, compare_type=True)
with context.begin_transaction():
    context.run_migrations()
