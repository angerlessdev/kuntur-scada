import pytest

from kuntur.adapters.narrators.template import FAILURES, TemplateNarrator
from kuntur.application.ports import IncidentContext
from kuntur.domain.alerts import AlertCode
from kuntur.domain.commands import CommandKind
from kuntur.domain.readings import FailureCause
from tests import incidents
from tests.factories import ups


async def _explain(context: IncidentContext) -> str:
    narration = await TemplateNarrator().explain(context)
    assert narration.source == "template"
    assert narration.likely_causes
    assert narration.checks
    return " ".join([narration.summary, *narration.likely_causes, *narration.checks])


@pytest.mark.parametrize("cause", list(FailureCause))
async def test_every_failure_cause_has_advice(cause: FailureCause) -> None:
    text = await _explain(incidents.lost_contact(cause))
    assert FAILURES[cause][0] in text
    assert "Fallaron 4 de las últimas 5 lecturas" in text


async def test_numbers_come_from_the_readings() -> None:
    assert "18 min de autonomía (87 % de batería)" in await _explain(incidents.on_battery())
    assert "al 15 %" in await _explain(incidents.battery_low())
    hot = await _explain(incidents.battery_hot())
    assert "44 °C" in hot
    assert "3.7 veces más rápido" in hot  # 2 ** ((44 - 25) / 10)
    assert "1 impacto(s) nuevo(s)" in await _explain(incidents.barrier_impact())
    assert "adelantado 612 s" in await _explain(incidents.clock_drift())


async def test_a_reboot_is_suggested_only_where_it_fixes_the_problem() -> None:
    narrator = TemplateNarrator()
    assert (await narrator.explain(incidents.clock_drift())).suggested_command is CommandKind.CAMERA_REBOOT
    for context in (incidents.on_battery(), incidents.battery_hot(), incidents.barrier_impact()):
        assert (await narrator.explain(context)).suggested_command is None


async def test_no_command_is_suggested_to_a_device_that_cannot_take_it() -> None:
    context = incidents.clock_drift()
    retired = IncidentContext(
        context.alert, context.device, context.recent_readings, context.failure_causes, 0, (), (), context.now
    )
    assert (await TemplateNarrator().explain(retired)).suggested_command is None


async def test_a_recurring_alert_asks_for_a_site_visit() -> None:
    context = incidents.incident(
        ups(),
        AlertCode.DEVICE_UNREACHABLE,
        incidents.failures("ups-01", FailureCause.TIMEOUT),
        previous_alerts=2,
    )
    assert "Es la 3.ª vez en 30 días" in await _explain(context)
