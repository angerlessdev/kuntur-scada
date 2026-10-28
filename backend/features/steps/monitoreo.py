"""Pasos de monitoreo: lecturas que llegan del campo y lo que ve el operador en pantalla."""

from __future__ import annotations

from behave import given, then, when
from behave.runner import Context

from kuntur.application.fleet import sync_fleet
from kuntur.domain.alerts import Alert, AlertCode, AlertState, Severity
from kuntur.domain.health import Health
from kuntur.domain.readings import FailureCause, Reading
from tests.factories import at, barrier, ups

COLORES = {"verde": Health.OK, "amarillo": Health.DEGRADED, "rojo": Health.DOWN, "gris": Health.UNKNOWN}
SEVERIDADES = {"crítica": Severity.CRITICAL, "de advertencia": Severity.WARNING}


@given('un UPS "{device_id}" en la flota')
def un_ups(context: Context, device_id: str) -> None:
    sync_fleet(context.app.uow, [ups(device_id)])
    context.device_id = device_id


@given('una barrera "{device_id}" en la flota')
def una_barrera(context: Context, device_id: str) -> None:
    sync_fleet(context.app.uow, [barrier(device_id)])
    context.device_id = device_id


def _registrar(context: Context, metrics: dict[str, float] | None) -> None:
    """Registra la siguiente lectura (cada 5 s). Sin métricas, el equipo no respondió."""
    taken_at = at(context.lecturas)
    context.lecturas += 1
    if metrics is None:
        reading = Reading.failed(context.device_id, taken_at, FailureCause.TIMEOUT)
    else:
        reading = Reading.ok(context.device_id, taken_at, metrics)
    context.app.record(reading)


@when("llegan las lecturas: {secuencia}")
def llegan_las_lecturas(context: Context, secuencia: str) -> None:
    for paso in secuencia.split(","):
        _registrar(context, {"load_pct": 40.0} if paso.strip() == "responde" else None)


@when("el equipo no responde en {n:d} lecturas seguidas")
def no_responde(context: Context, n: int) -> None:
    for _ in range(n):
        _registrar(context, None)


@when("el equipo responde en {n:d} lecturas seguidas")
def responde(context: Context, n: int) -> None:
    for _ in range(n):
        _registrar(context, {"load_pct": 40.0})


@given("que el equipo perdió la comunicación")
def perdio_la_comunicacion(context: Context) -> None:
    no_responde(context, 4)
    assert _activa(context, AlertCode.DEVICE_UNREACHABLE) is not None


@when("la batería marca {valores} °C")
def la_bateria_marca(context: Context, valores: str) -> None:
    for valor in valores.split(","):
        _registrar(context, {"battery_temp_c": float(valor)})


def _activa(context: Context, code: AlertCode) -> Alert | None:
    activas = context.app.queries.alerts(state=AlertState.ACTIVE, device_id=context.device_id, limit=50)
    return next((alert for alert in activas if alert.code is code), None)


@then("el equipo se ve en {color}")
def se_ve_en(context: Context, color: str) -> None:
    health = context.app.queries.device(context.device_id).health
    assert health is COLORES[color], f"Se ve {health}, se esperaba {color}"


@then("no hay alertas activas")
def no_hay_alertas(context: Context) -> None:
    activas = context.app.queries.alerts(state=AlertState.ACTIVE, device_id=context.device_id, limit=50)
    assert activas == [], f"Alertas activas: {[alert.code for alert in activas]}"


@then('hay una alerta {severidad} "{code:w}" activa')
def hay_una_alerta(context: Context, severidad: str, code: str) -> None:
    alert = _activa(context, AlertCode(code))
    assert alert is not None, f"No hay una alerta {code} activa"
    assert alert.severity is SEVERIDADES[severidad]


@then('la alerta "{code:w}" sigue activa')
def sigue_activa(context: Context, code: str) -> None:
    assert _activa(context, AlertCode(code)) is not None, f"La alerta {code} ya no está activa"


@then('la alerta "{code:w}" queda resuelta')
def queda_resuelta(context: Context, code: str) -> None:
    assert _activa(context, AlertCode(code)) is None, f"La alerta {code} sigue activa"
    resueltas = context.app.queries.alerts(state=AlertState.RESOLVED, device_id=context.device_id, limit=50)
    assert any(alert.code is AlertCode(code) for alert in resueltas)
