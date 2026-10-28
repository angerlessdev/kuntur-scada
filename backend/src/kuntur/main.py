"""Entry points: ``kuntur-api`` runs the platform; ``uvicorn --factory kuntur.main:create_app`` too."""

from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI

from kuntur.adapters.api.app import create_api
from kuntur.adapters.fleet_file import FleetFileError
from kuntur.bootstrap import ConfigurationError, build_application
from kuntur.config import Settings


def create_app() -> FastAPI:
    return create_api(build_application(Settings()))


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings()
    try:
        application = build_application(settings)
    except (ConfigurationError, FleetFileError) as exc:
        raise SystemExit(f"Kuntur no puede arrancar: {exc}") from exc
    uvicorn.run(create_api(application), host=settings.host, port=settings.port, server_header=False)


if __name__ == "__main__":
    run()
