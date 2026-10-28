# language: es
Característica: Órdenes a los equipos, siempre auditadas
  Toda orden enviada a un equipo de campo queda registrada con su autor y su resultado,
  también cuando el equipo no responde. Solo un operador puede enviarlas.

  Antecedentes:
    Dada una barrera "barrera-via-03" en la flota

  Escenario: El operador abre la barrera
    Dado que la sesión es de un operador "operador.turno1"
    Cuando envía la orden "BARRIER_OPEN" a "barrera-via-03"
    Entonces la orden queda "SUCCEEDED"
    Y la auditoría registra a "operador.turno1" como autor

  Escenario: Un visitante solo puede mirar
    Dado que la sesión es de un visitante "auditor.externo"
    Cuando envía la orden "BARRIER_OPEN" a "barrera-via-03"
    Entonces la orden es rechazada por permisos
    Y la auditoría no registra ninguna orden

  Escenario: El equipo no responde a tiempo
    Dado que la sesión es de un operador "operador.turno1"
    Y la barrera tarda más de lo permitido en responder
    Cuando envía la orden "BARRIER_CLOSE" a "barrera-via-03"
    Entonces la orden queda "FAILED" con el detalle "El equipo no respondió en 0.05 s"
    Y la auditoría registra a "operador.turno1" como autor

  Escenario: Una orden que no es de ese tipo de equipo no llega a enviarse
    Dado que la sesión es de un operador "operador.turno1"
    Cuando envía la orden "CAMERA_REBOOT" a "barrera-via-03"
    Entonces la orden es rechazada por no corresponder al equipo
    Y la auditoría no registra ninguna orden

  Escenario: Un reinicio ordenado no dispara la alarma de comunicación
    Dada una cámara "camara-via-03" en la flota
    Y que la sesión es de un operador "operador.turno1"
    Cuando envía la orden "CAMERA_REBOOT" a "camara-via-03"
    Y el equipo no responde en 12 lecturas seguidas
    Entonces no hay alertas activas
    Y el equipo se ve en amarillo
    Cuando el equipo no responde en 8 lecturas seguidas
    Entonces hay una alerta crítica "DEVICE_UNREACHABLE" activa
