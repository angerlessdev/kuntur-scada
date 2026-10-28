# language: es
Característica: Histéresis en la temperatura de la batería del UPS
  Por cada 10 °C sobre 25 °C, una batería de plomo dura la mitad. La alerta salta sobre 40 °C,
  confirmada en 3 de las últimas 4 lecturas, y se apaga solo cuando 3 lecturas seguidas bajan
  de 37 °C. Así, un valor que ronda el límite no la enciende y la apaga a cada rato.

  Antecedentes:
    Dado un UPS "ups-norte-01" en la flota

  Escenario: Dos picos sueltos no confirman nada
    Cuando la batería marca 41, 36, 42, 36 °C
    Entonces no hay alertas activas

  Escenario: Entre los dos límites la alerta se mantiene
    Cuando la batería marca 41, 42, 43 °C
    Entonces hay una alerta de advertencia "UPS_BATTERY_HOT" activa
    Y el equipo se ve en amarillo
    Cuando la batería marca 39, 38, 39.9, 38 °C
    Entonces la alerta "UPS_BATTERY_HOT" sigue activa
    Cuando la batería marca 36, 35, 36 °C
    Entonces la alerta "UPS_BATTERY_HOT" queda resuelta
    Y el equipo se ve en verde
