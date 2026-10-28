import pytest

from kuntur.application.ports import CommandExecutionError
from kuntur.domain.commands import CommandKind, CommandStatus
from kuntur.domain.devices import Device
from kuntur.domain.errors import CommandNotAllowedError, NotFoundError, PermissionDeniedError
from kuntur.domain.events import CommandFinished
from kuntur.domain.security import Actor, Role
from tests.factories import T0, barrier, ups
from tests.fakes import App, build_app

OPERATOR = Actor("operador", Role.OPERATOR)
VIEWER = Actor("visita", Role.VIEWER)


def _audit(app: App) -> list[CommandStatus]:
    return [c.status for c in app.queries.commands(device_id=None, limit=10)]


async def test_a_successful_command_is_audited_with_its_author() -> None:
    app = build_app(barrier())
    app.driver.command_results.append("Barrera abierta")
    command = await app.issue(OPERATOR, "barrera-01", CommandKind.BARRIER_OPEN)
    assert (command.status, command.detail, command.requested_by) == (
        CommandStatus.SUCCEEDED,
        "Barrera abierta",
        "operador",
    )
    assert (command.requested_at, command.finished_at) == (T0, T0)
    assert app.queries.commands(device_id="barrera-01", limit=10) == [command]
    assert [e.command for e in app.bus.of_type(CommandFinished)] == [command]
    assert app.driver.executed == [("barrera-01", CommandKind.BARRIER_OPEN)]


async def test_the_attempt_is_audited_before_the_device_acts() -> None:
    app = build_app(barrier())
    seen_while_executing: list[CommandStatus] = []
    app.driver.on_execute = lambda: seen_while_executing.extend(_audit(app))
    await app.issue(OPERATOR, "barrera-01", CommandKind.BARRIER_OPEN)
    assert seen_while_executing == [CommandStatus.PENDING]
    assert _audit(app) == [CommandStatus.SUCCEEDED]


async def test_a_viewer_cannot_send_commands() -> None:
    app = build_app(barrier())
    with pytest.raises(PermissionDeniedError):
        await app.issue(VIEWER, "barrera-01", CommandKind.BARRIER_OPEN)
    assert app.driver.executed == []
    assert _audit(app) == []


async def test_an_unknown_device_is_rejected() -> None:
    with pytest.raises(NotFoundError):
        await build_app().issue(OPERATOR, "fantasma", CommandKind.BARRIER_OPEN)


@pytest.mark.parametrize(
    ("device", "kind"),
    [(ups(), CommandKind.BARRIER_OPEN), (ups(active=False), CommandKind.UPS_BATTERY_TEST)],
    ids=["wrong-kind", "out-of-service"],
)
async def test_a_command_the_device_cannot_take_never_reaches_it(device: Device, kind: CommandKind) -> None:
    app = build_app(device)
    with pytest.raises(CommandNotAllowedError):
        await app.issue(OPERATOR, "ups-01", kind)
    assert app.driver.executed == []
    assert _audit(app) == []


async def test_a_refusal_from_the_device_is_a_failed_command() -> None:
    app = build_app(ups())
    app.driver.command_results.append(CommandExecutionError("Prueba de batería en curso"))
    command = await app.issue(OPERATOR, "ups-01", CommandKind.UPS_BATTERY_TEST)
    assert (command.status, command.detail) == (CommandStatus.FAILED, "Prueba de batería en curso")


async def test_a_device_that_does_not_answer_fails_the_command() -> None:
    app = build_app(ups(), timeout_s=0.05)
    app.driver.delay_s = 1.0
    command = await app.issue(OPERATOR, "ups-01", CommandKind.UPS_SILENCE_ALARM)
    assert (command.status, command.detail) == (CommandStatus.FAILED, "El equipo no respondió en 0.05 s")
    assert _audit(app) == [CommandStatus.FAILED]


async def test_a_crashing_driver_still_closes_the_audit_entry(caplog: pytest.LogCaptureFixture) -> None:
    app = build_app(ups())
    app.driver.command_results.append(KeyError("x"))
    command = await app.issue(OPERATOR, "ups-01", CommandKind.UPS_SILENCE_ALARM)
    assert (command.status, command.detail) == (
        CommandStatus.FAILED,
        "Error interno del controlador (KeyError)",
    )
    assert "crashed" in caplog.text
