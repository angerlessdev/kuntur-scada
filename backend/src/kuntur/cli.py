"""``kuntur-db upgrade``: creates the database if needed and applies the pending migrations."""

from __future__ import annotations

import argparse

from kuntur.adapters.persistence.sql.database import create_sql_engine, ensure_database, upgrade
from kuntur.config import Settings


def db() -> None:
    parser = argparse.ArgumentParser(prog="kuntur-db", description="Base de datos de Kuntur SCADA")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("upgrade", help="crea la base si no existe y aplica las migraciones pendientes")
    parser.parse_args()
    settings = Settings()
    if settings.database_url is None:
        raise SystemExit("Set KUNTUR_DATABASE_URL")
    url = settings.database_url.get_secret_value()
    created = ensure_database(url)
    engine = create_sql_engine(url, pool_size=1)
    try:
        upgrade(engine)
    finally:
        engine.dispose()
    print("Base de datos creada y migrada" if created else "Base de datos al día")
