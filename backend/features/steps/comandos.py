"""Pasos de control supervisorio: quién envía la orden, qué contesta el equipo, qué queda auditado."""

from __future__ import annotations

import asyncio

from behave import given, then, when
from behave.runner import Context

from kuntur.domain.commands import CommandKind, CommandStatus
from kuntur.domain.errors import CommandNotAllowedError, PermissionDeniedError
from kuntur.domain.security import Actor, Role


@given('que la sesión es de un operador "{username}"')
def sesion_de_operador(context: Context, username: str) -> None:
    context.actor = Actor(username, Role.OPERATOR)


@given('que la sesión es de un visitante "{username}"')
def sesion_de_visitante(context: Context, username: str) -> None:
    context.actor = Actor(username, Role.VIEWER)


@given("la barrera tarda más de lo permitido en responder")
def barrera_lenta(context: Context) -> None:
    context.app.driver.delay_s = 1.0


@when('envía la orden "{kind:w}" a "{device_id}"')
def envia_la_orden(context: Context, kind: str, device_id: str) -> None:
    context.command = context.error = None
    try:
        context.command = asyncio.run(context.app.issue(context.actor, device_id, CommandKind(kind)))
    except (PermissionDeniedError, CommandNotAllowedError) as exc:
        context.error = exc


@then('la orden queda "{status:w}" con el detalle "{detail}"')
def queda_con_detalle(context: Context, status: str, detail: str) -> None:
    queda(context, status)
    assert context.command.detail == detail, f"Detalle: {context.command.detail!r}"


@then('la orden queda "{status:w}"')
def queda(context: Context, status: str) -> None:
    assert context.command is not None, f"La orden fue rechazada: {context.error}"
    assert context.command.status is CommandStatus(status), f"Quedó {context.command.status}"


@then("la orden es rechazada por permisos")
def rechazada_por_permisos(context: Context) -> None:
    assert isinstance(context.error, PermissionDeniedError), f"Resultado: {context.command or context.error}"


@then("la orden es rechazada por no corresponder al equipo")
def rechazada_por_tipo(context: Context) -> None:
    assert isinstance(context.error, CommandNotAllowedError), f"Resultado: {context.command or context.error}"


@then('la auditoría registra a "{username}" como autor')
def auditoria_registra(context: Context, username: str) -> None:
    [registro] = context.app.queries.commands(device_id=None, limit=10)
    assert registro.requested_by == username
    assert registro.status is not CommandStatus.PENDING, "La auditoría quedó abierta"


@then("la auditoría no registra ninguna orden")
def auditoria_vacia(context: Context) -> None:
    assert context.app.queries.commands(device_id=None, limit=10) == []
