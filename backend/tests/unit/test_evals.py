"""The template is the floor every narrator is measured against, so it must pass its own evals."""

import pytest

from evals.cases import CASES, EvalCase
from evals.graders import grade, plain
from evals.run import evaluate, report
from kuntur.adapters.narrators.template import TemplateNarrator
from kuntur.application.ports import Narration
from kuntur.domain.commands import CommandKind


async def test_the_template_passes_every_case() -> None:
    results = await evaluate(TemplateNarrator())
    failures = {r.case.name: [g for g in r.grades if not g.passed] for r in results if not r.passed}
    assert failures == {}
    assert "11 de 11 casos aprobados" in report(results, "template")


def _case(name: str) -> EvalCase:
    return next(case for case in CASES if case.name == name)


@pytest.mark.parametrize(
    ("name", "narration", "failing"),
    [
        (
            "reloj-desfasado",
            Narration("El reloj está desfasado.", ("NTP",), ("Revisar NTP",), None, "x"),
            {"orden adecuada", "menciona lo esencial"},
        ),
        (
            "texto-inyectado",
            Narration("Todo está bien.", ("Nada",), ("Nada",), CommandKind.UPS_BATTERY_TEST, "x"),
            {"orden adecuada", "no repite lo inyectado"},
        ),
        (
            "sin-comunicacion-rechazada",
            Narration("The device is down; check camara-01.", ("x",), ("y",), None, "x"),
            {"menciona lo esencial", "en español", "no habla de otros equipos"},
        ),
    ],
    ids=["missing-numbers-and-fix", "followed-the-injection", "english-and-wrong-device"],
)
def test_the_graders_catch_what_an_operator_would_complain_about(
    name: str, narration: Narration, failing: set[str]
) -> None:
    assert {g.grader for g in grade(_case(name), narration) if not g.passed} == failing


def test_matching_ignores_accents_and_case() -> None:
    assert plain("Energía ELÉCTRICA") == "energia electrica"
