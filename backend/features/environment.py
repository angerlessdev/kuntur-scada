"""Hooks de behave: cada escenario arranca con la aplicación nueva, sobre los adaptadores en memoria."""

from behave.model import Scenario
from behave.runner import Context

from tests.fakes import build_app

TIMEOUT_S = 0.05
"""Tiempo máximo de respuesta de los equipos en los escenarios (corto, para que corran rápido)."""


def before_scenario(context: Context, scenario: Scenario) -> None:
    context.app = build_app(timeout_s=TIMEOUT_S)
    context.lecturas = 0
