# language: es
Característica: Confirmación de la pérdida de comunicación
  Para no despertar a un técnico por un paquete perdido,
  como operador del centro de control
  quiero que la alarma «sin comunicación» salte solo cuando la falla está confirmada
  y que no parpadee cuando el equipo vuelve.

  Las lecturas llegan cada 5 segundos. La alarma salta con 4 fallas en las últimas 5 lecturas,
  se apaga con 2 respuestas seguidas y dura al menos 30 segundos.

  Antecedentes:
    Dado un UPS "ups-norte-01" en la flota

  Escenario: Una falla aislada es ruido, no una alarma
    Cuando llegan las lecturas: responde, falla, responde
    Entonces el equipo se ve en verde
    Y no hay alertas activas

  Escenario: Una falla sin confirmar se ve en amarillo, nunca en verde
    Cuando llegan las lecturas: responde, falla
    Entonces el equipo se ve en amarillo
    Y no hay alertas activas

  Escenario: Cuatro fallas seguidas confirman la pérdida
    Cuando el equipo no responde en 4 lecturas seguidas
    Entonces hay una alerta crítica "DEVICE_UNREACHABLE" activa
    Y el equipo se ve en rojo

  Escenario: Al volver, la alarma espera su tiempo mínimo antes de apagarse
    Dado que el equipo perdió la comunicación
    Cuando el equipo responde en 2 lecturas seguidas
    Entonces la alerta "DEVICE_UNREACHABLE" sigue activa
    Cuando el equipo responde en 4 lecturas seguidas
    Entonces la alerta "DEVICE_UNREACHABLE" queda resuelta
    Y el equipo se ve en verde
