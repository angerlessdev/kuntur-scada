import asyncio
from datetime import timedelta

import pytest

from kuntur.adapters.narrators.template import TemplateNarrator
from kuntur.application.explain import FALLBACK_TTL, MAX_CHECKS, MAX_TEXT, ExplainAlert
from kuntur.application.ports import IncidentContext, Narration, NarratorUnavailable
from kuntur.domain.alerts import AlertState
from kuntur.domain.commands import CommandKind
from kuntur.domain.errors import NotFoundError
from tests.factories import failed, ups
from tests.fakes import App, build_app


class Scripted:
    """A narrator that answers whatever the test needs, and counts how often it was asked."""

    def __init__(self, answer: Narration | Exception | None = None, delay_s: float = 0.0) -> None:
        self.answer = answer
        self.delay_s = delay_s
        self.calls = 0

    async def explain(self, context: IncidentContext) -> Narration:
        self.calls += 1
        if self.delay_s:
            await asyncio.sleep(self.delay_s)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer or Narration("Resumen del modelo", ("Causa",), ("Revisar",), None, "claude:prueba")


def _with_alert(narrator: Scripted, budget_s: float = 1.0) -> tuple[App, ExplainAlert, str]:
    app = build_app(ups())
    for i in range(4):
        app.record(failed(i))
    [alert] = app.queries.alerts(state=AlertState.ACTIVE, device_id=None, limit=1)
    app.clock.advance(timedelta(minutes=1))  # the operator asks a minute after the alert was raised
    explain = ExplainAlert(app.uow, narrator, TemplateNarrator(), app.clock, budget_s=budget_s)
    return app, explain, alert.id


async def test_the_preferred_narrator_explains_and_is_credited() -> None:
    _, explain, alert_id = _with_alert(Scripted())
    explanation = await explain(alert_id)
    assert (explanation.narration.source, explanation.fallback_reason) == ("claude:prueba", None)


@pytest.mark.parametrize(
    ("narrator", "reason"),
    [
        (Scripted(NarratorUnavailable("no hay conexión con Claude")), "no hay conexión con Claude"),
        (Scripted(delay_s=5), "tiempo agotado"),
        (Scripted(RuntimeError("cadena de conexión con la clave")), "error inesperado"),
    ],
    ids=["unavailable", "too-slow", "crash"],
)
async def test_any_failure_falls_back_to_the_template_with_a_safe_reason(
    narrator: Scripted, reason: str
) -> None:
    _, explain, alert_id = _with_alert(narrator, budget_s=0.05)
    explanation = await explain(alert_id)
    assert explanation.narration.source == "template"
    assert explanation.fallback_reason == reason


async def test_the_guard_drops_a_command_the_device_cannot_take_and_caps_the_texts() -> None:
    loud = Narration(
        "x" * 1000,
        tuple(f"causa {i}" for i in range(9)),
        tuple(f"revisar {i}" for i in range(9)),
        CommandKind.CAMERA_REBOOT,
        "claude:prueba",
    )
    _, explain, alert_id = _with_alert(Scripted(loud))
    narration = (await explain(alert_id)).narration
    assert narration.suggested_command is None
    assert len(narration.summary) == MAX_TEXT
    assert len(narration.checks) == MAX_CHECKS


async def test_an_explanation_is_kept_until_the_alert_changes_state() -> None:
    narrator = Scripted()
    app, explain, alert_id = _with_alert(narrator)
    await explain(alert_id)
    await explain(alert_id)
    assert narrator.calls == 1
    with app.uow() as uow:
        alert = uow.alerts.get(alert_id)
        assert alert is not None
        alert.resolve(app.clock.now())
        uow.alerts.update(alert)
        uow.commit()
    await explain(alert_id)
    assert narrator.calls == 2


async def test_a_template_answered_for_a_failure_is_retried_later() -> None:
    narrator = Scripted(NarratorUnavailable("no hay conexión con Claude"))
    app, explain, alert_id = _with_alert(narrator)
    await explain(alert_id)
    await explain(alert_id)
    assert narrator.calls == 1
    app.clock.advance(FALLBACK_TTL + timedelta(seconds=1))
    narrator.answer = None
    assert (await explain(alert_id)).narration.source == "claude:prueba"


async def test_the_context_counts_causes_history_and_allowed_commands() -> None:
    _, explain, alert_id = _with_alert(Scripted())
    context = explain.context(alert_id)
    assert context.failure_causes == {failed(0).cause: 4}
    assert (context.previous_alerts, context.allowed_commands) == (
        0,
        (CommandKind.UPS_BATTERY_TEST, CommandKind.UPS_SILENCE_ALARM),
    )
    with pytest.raises(NotFoundError):
        explain.context("no-existe")
