"""Deterministic explanations, written from how each device and each failure behaves.

Always available, instant and free: the fallback when the language model cannot answer, and the
baseline it has to beat in the evals. Numbers come only from the incident's own readings.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from kuntur.application.ports import IncidentContext, Narration
from kuntur.domain.alerts import AlertCode
from kuntur.domain.commands import CommandKind
from kuntur.domain.lifetime import battery_aging_factor
from kuntur.domain.readings import FailureCause

Advice = tuple[str, tuple[str, ...], tuple[str, ...]]
"""What a failure means, its likely causes and what to check, in that order."""

FAILURES: Mapping[FailureCause, Advice] = {
    FailureCause.TIMEOUT: (
        "el equipo no contesta a tiempo",
        (
            "El equipo está colgado o reiniciándose",
            "Se perdió la ruta de red hacia el equipo",
            "El enlace está saturado",
        ),
        (
            "Hacer ping al equipo desde el centro de control",
            "Confirmar que el equipo tiene energía",
            "Revisar el puerto del switch y el cable de la estación",
        ),
    ),
    FailureCause.CONNECTION_REFUSED: (
        "el equipo está en la red pero su servicio no atiende",
        (
            "El servicio del equipo se detuvo o se está reiniciando",
            "El equipo arrancó sin su servicio de comunicaciones",
            "El puerto declarado en la flota no es el del equipo",
        ),
        (
            "Confirmar en sitio que el equipo terminó de arrancar",
            "Reiniciar el servicio de comunicaciones del equipo",
            "Verificar el puerto declarado en la flota",
        ),
    ),
    FailureCause.UNREACHABLE: (
        "no hay ruta de red hacia el equipo",
        (
            "Se cayó el enlace de la estación",
            "Cambió la dirección del equipo",
            "Falló el switch de la estación",
        ),
        (
            "Revisar el enlace de la estación",
            "Confirmar la dirección del equipo",
            "Revisar el switch y su energía",
        ),
    ),
    FailureCause.CONNECTION_LOST: (
        "la conexión se abre y se corta antes de la respuesta",
        (
            "Un enlace inestable: cable, conector o puerto del switch",
            "El equipo se reinicia en bucle",
            "El enlace está saturado o con interferencia",
        ),
        (
            "Revisar cable y conectores",
            "Ver los errores del puerto en el switch",
            "Ver si el equipo se reinicia solo",
        ),
    ),
    FailureCause.AUTH_FAILED: (
        "el equipo rechaza las credenciales de Kuntur",
        ("Cambió la contraseña del equipo", "La cuenta del equipo se bloqueó"),
        (
            "Confirmar la contraseña vigente del equipo",
            "Actualizar la credencial configurada en Kuntur",
            "Revisar si la cuenta del equipo quedó bloqueada",
        ),
    ),
    FailureCause.PROTOCOL_ERROR: (
        "algo responde, pero no en el protocolo esperado",
        ("Otro servicio ocupa el puerto del equipo", "Una actualización de firmware cambió el protocolo"),
        ("Verificar qué servicio atiende ese puerto", "Revisar la versión de firmware del equipo"),
    ),
    FailureCause.INVALID_DATA: (
        "el equipo responde con valores imposibles",
        ("Un sensor del equipo está fallando", "Una escala mal configurada en el equipo"),
        ("Revisar los sensores del equipo", "Comparar con una medición en sitio"),
    ),
    FailureCause.DEVICE_FAULT: (
        "el equipo informa una falla interna o está reiniciando",
        ("Un reinicio en curso", "Una falla interna del equipo"),
        ("Esperar a que termine el reinicio", "Revisar el registro de eventos del equipo"),
    ),
    FailureCause.UNKNOWN: (
        "la falla no se pudo clasificar",
        ("Una falla no prevista del controlador",),
        ("Revisar el registro de Kuntur para este equipo",),
    ),
}


def _latest(context: IncidentContext, metric: str) -> float | None:
    for reading in reversed(context.recent_readings):
        if (value := reading.metric(metric)) is not None:
            return value
    return None


def _number(value: float) -> str:
    return f"{value:.1f}".rstrip("0").rstrip(".")


def _unreachable(context: IncidentContext) -> Narration:
    causes = context.failure_causes
    cause = max(causes, key=lambda c: causes[c]) if causes else FailureCause.UNKNOWN
    meaning, likely, checks = FAILURES[cause]
    failed = sum(1 for r in context.recent_readings if not r.answered)
    device = context.device
    summary = (
        f"Sin comunicación con {device.name} ({device.site}): {meaning}. "
        f"Fallaron {failed} de las últimas {len(context.recent_readings)} lecturas."
    )
    return _narration(summary, likely, checks, None, context)


def _on_battery(context: IncidentContext) -> Narration:
    autonomy, charge = _latest(context, "autonomy_min"), _latest(context, "battery_charge_pct")
    state = ""
    if autonomy is not None and charge is not None:
        state = (
            f" Con la carga actual le quedan unos {_number(autonomy)} min de autonomía"
            f" ({_number(charge)} % de batería)."
        )
    summary = f"{context.device.name} alimenta la carga desde la batería: no llega energía de la red.{state}"
    likely = (
        "Un corte de energía en la estación",
        "Una falla del tablero o del interruptor de entrada",
        "Se abrió la protección de entrada del UPS",
    )
    checks = (
        "Confirmar con mantenimiento eléctrico si hay un corte en la estación",
        "Revisar el tablero y el interruptor de entrada del UPS",
        "Si el corte se prolonga, priorizar las cargas críticas antes de que se agote la batería",
    )
    return _narration(summary, likely, checks, None, context)


def _battery_low(context: IncidentContext) -> Narration:
    charge, autonomy = _latest(context, "battery_charge_pct"), _latest(context, "autonomy_min")
    level = f" está al {_number(charge)} %" if charge is not None else " está baja"
    tail = f": sin red, el UPS se apagará en unos {_number(autonomy)} min" if autonomy is not None else ""
    summary = f"La batería de {context.device.name}{level}{tail}."
    likely = (
        "El UPS lleva tiempo en batería por un corte de energía",
        "Baterías desgastadas que ya no retienen carga",
        "El cargador del UPS no está cargando",
    )
    checks = (
        "Confirmar si sigue el corte de energía",
        "Avisar a las estaciones que dependen de este UPS",
        "Si hay red y la carga no sube, revisar el cargador y las baterías",
    )
    return _narration(summary, likely, checks, None, context)


def _battery_hot(context: IncidentContext) -> Narration:
    temperature = _latest(context, "battery_temp_c")
    summary = f"La batería de {context.device.name} está muy caliente."
    if temperature is not None:
        factor = battery_aging_factor(temperature)
        summary = (
            f"La batería de {context.device.name} está a {_number(temperature)} °C. Por cada 10 °C"
            f" sobre 25 °C una batería dura la mitad: a esta temperatura envejece {_number(factor)} veces"
            " más rápido."
        )
    likely = (
        "Falló el aire acondicionado de la sala eléctrica",
        "La ventilación del gabinete está obstruida",
        "Baterías al final de su vida que se calientan al cargar",
    )
    checks = (
        "Revisar el aire acondicionado de la sala eléctrica",
        "Despejar la ventilación del gabinete",
        "Si estuvo caliente por semanas, programar el cambio de baterías",
    )
    return _narration(summary, likely, checks, None, context)


def _impact(context: IncidentContext) -> Narration:
    counts = [v for r in context.recent_readings if (v := r.metric("impacts_total")) is not None]
    growth = counts[-1] - counts[-2] if len(counts) >= 2 and counts[-1] > counts[-2] else None  # noqa: PLR2004
    what = f"{_number(growth)} impacto(s) nuevo(s)" if growth is not None else "un impacto nuevo"
    summary = f"{context.device.name} registró {what}: el brazo pudo quedar dañado o desalineado."
    likely = (
        "Un vehículo golpeó el brazo de la barrera",
        "La barrera bajó con un vehículo debajo: el detector de presencia pudo fallar",
    )
    checks = (
        "Ver la cámara de la vía en el momento del impacto",
        "Revisar el brazo, su anclaje y su resorte",
        "Probar el detector de presencia antes de habilitar la vía",
    )
    return _narration(summary, likely, checks, None, context)


def _clock_drift(context: IncidentContext) -> Narration:
    offset = _latest(context, "clock_offset_s")
    state = "desfasado"
    if offset is not None:
        state = f"{'adelantado' if offset > 0 else 'atrasado'} {_number(abs(offset))} s"
    summary = (
        f"El reloj de {context.device.name} está {state}: las grabaciones quedan con la hora "
        "equivocada y pierden valor como evidencia."
    )
    likely = (
        "La cámara perdió la sincronización con su servidor NTP",
        "El servidor NTP no es alcanzable desde la cámara",
        "Se agotó la pila del reloj interno de la cámara",
    )
    checks = (
        "Verificar el servidor NTP configurado en la cámara",
        "Confirmar que la cámara llega a su servidor NTP",
        "Reiniciar la cámara: al arrancar se vuelve a sincronizar",
    )
    return _narration(summary, likely, checks, CommandKind.CAMERA_REBOOT, context)


def _narration(
    summary: str,
    likely: tuple[str, ...],
    checks: tuple[str, ...],
    command: CommandKind | None,
    context: IncidentContext,
) -> Narration:
    if context.previous_alerts:
        times = context.previous_alerts + 1
        checks = (*checks, f"Es la {times}.ª vez en 30 días: programar una revisión en sitio")
    allowed = command if command in context.allowed_commands else None
    return Narration(summary, likely, checks, allowed, "template")


WRITERS: Mapping[AlertCode, Callable[[IncidentContext], Narration]] = {
    AlertCode.DEVICE_UNREACHABLE: _unreachable,
    AlertCode.UPS_ON_BATTERY: _on_battery,
    AlertCode.UPS_BATTERY_LOW: _battery_low,
    AlertCode.UPS_BATTERY_HOT: _battery_hot,
    AlertCode.BARRIER_IMPACT: _impact,
    AlertCode.CAMERA_CLOCK_DRIFT: _clock_drift,
}


class TemplateNarrator:
    async def explain(self, context: IncidentContext) -> Narration:
        return WRITERS[context.alert.code](context)
