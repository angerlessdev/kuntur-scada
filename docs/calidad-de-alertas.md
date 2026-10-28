# Calidad de las alertas

Medido el 2026-10-28 con `python -m evals.alert_quality` sobre la
plataforma completa (docker compose): el simulador reproduce cada incidente y registra la
verdad de terreno; el script compara con las alertas que levantó Kuntur. Cada escenario
corrió una vez: es una prueba con verdad de terreno, no una estadística.

- **Precisión: 100 %** (9 alertas correctas, 0 falsas alarmas)
- **Recall: 100 %** (9 de 9 incidentes que debían alertar)
- **Silencio correcto: 5 de 5** incidentes que no debían alertar
- **Detección:** mediana 16 s, peor caso 37 s (lecturas cada 5 s)

| Equipo | Incidente | Alerta esperada | Alertas levantadas | Resultado | Detección |
|---|---|---|---|---|---|
| `ups-norte-01` | `corte-de-energia` | UPS_ON_BATTERY | UPS_ON_BATTERY | ✅ alertó | 7 s |
| `ups-sur-01` | `bateria-caliente` | UPS_BATTERY_HOT | UPS_BATTERY_HOT | ✅ alertó | 37 s |
| `barrera-norte-01` | `equipo-caido` | DEVICE_UNREACHABLE | DEVICE_UNREACHABLE | ✅ alertó | 17 s |
| `barrera-norte-02` | `perdida-aislada` | ninguna | ninguna | ✅ no alertó | - |
| `barrera-sur-01` | `red-inestable` | DEVICE_UNREACHABLE | DEVICE_UNREACHABLE, DEVICE_UNREACHABLE | ✅ alertó | 37 s |
| `camara-norte-01` | `reloj-desfasado` | CAMERA_CLOCK_DRIFT | CAMERA_CLOCK_DRIFT | ✅ alertó | 7 s |
| `camara-sur-01` | `sin-respuesta` | DEVICE_UNREACHABLE | DEVICE_UNREACHABLE | ✅ alertó | 17 s |
| `ups-norte-01` | `enlace-lento` | ninguna | ninguna | ✅ no alertó | - |
| `ups-sur-01` | `sensor-sin-dato` | ninguna | ninguna | ✅ no alertó | - |
| `barrera-norte-01` | `impacto` | BARRIER_IMPACT | BARRIER_IMPACT | ✅ alertó | 1 s |
| `barrera-norte-02` | `sin-respuesta` | DEVICE_UNREACHABLE | DEVICE_UNREACHABLE | ✅ alertó | 16 s |
| `barrera-sur-01` | `perdida-aislada` | ninguna | ninguna | ✅ no alertó | - |
| `camara-norte-01` | `equipo-caido` | DEVICE_UNREACHABLE | DEVICE_UNREACHABLE | ✅ alertó | 16 s |
| `camara-sur-01` | `perdida-aislada` | ninguna | ninguna | ✅ no alertó | - |

**Red inestable:** la conexión se cortó 3 veces en 2 minutos (20 s arriba, 20 s cortada) y la
alerta se levantó 2 veces: a los 37 s, por 50 s; a los 117 s, por 35 s. Una alerta dura al menos 30 s y no vuelve
a levantarse antes de 30 s de resuelta, así que sigue activa entre cortes cercanos en vez de
encenderse y apagarse con cada uno.

Los incidentes que no deben alertar importan tanto como los otros: una pérdida aislada de
4 s, un enlace lento que sigue dentro del tiempo de espera y un sensor que deja de dar valor
(lectura parcial: el equipo se ve en amarillo, sin alarma).
