# kuntur-sim: simulador de equipos de campo

Simula la flota declarada en [`config/fleet.json`](../config/fleet.json) con protocolos reales, para
que la plataforma se pruebe contra algo que se comporta como el campo: responde, se cuelga, se
calienta y falla.

| Equipo  | Protocolo                   | Qué simula                                                   |
|---------|-----------------------------|--------------------------------------------------------------|
| UPS     | Modbus TCP (registros 0–7)  | red eléctrica, carga, descarga de batería, temperatura       |
| Barrera | WebSocket con mensajes JSON | tráfico (proceso de Poisson), ciclos, impactos, motor        |
| Cámara  | HTTP con Digest SHA-256     | deriva del reloj; un reinicio lo resincroniza, como con NTP  |

Los modelos físicos (`models.py`) son máquinas de estado puras: no hacen E/S y con la misma semilla
cuentan la misma historia, así que las pruebas y el informe de calidad de alertas son reproducibles.

## Fallas de red

Cada equipo tiene delante un proxy TCP (`faults.py`) que rompe la red sin saber de protocolos, así
que cada driver de la plataforma tiene que clasificar la falla por su cuenta:

| Modo       | Efecto                                                    | Como en el campo                  |
|------------|-----------------------------------------------------------|-----------------------------------|
| `DOWN`     | nadie escucha: la conexión se rechaza                     | equipo sin energía                |
| `TIMEOUT`  | acepta la conexión y no contesta nunca                    | equipo colgado, ruta perdida      |
| `SLOW`     | cada respuesta llega con `delay_s` de retraso             | enlace saturado                   |
| `FLAPPING` | se corta y vuelve cada `period_s`                         | cable flojo, puerto de switch     |

## Escenarios con verdad de terreno

`POST /sim/scenarios/{nombre}` reproduce un incidente y lo registra en `GET /sim/incidents` con la
alerta que la plataforma debería levantar, o con `null` cuando levantar una sería una falsa alarma
(`perdida-aislada`, `enlace-lento`, `sensor-sin-dato`). Con eso se mide la precisión y el recall
de las alertas.

## Uso

```bash
export KUNTUR_SIM_CAMERA_PASSWORD=...   # obligatoria; ver .env.example
uv run kuntur-sim --fleet config/fleet.json
```

La API de control queda en `http://127.0.0.1:15000/docs`. Ejemplos:

```bash
curl -X PUT  localhost:15000/sim/devices/ups-norte-01/fault -H 'content-type: application/json' -d '{"mode": "TIMEOUT"}'
curl -X POST localhost:15000/sim/scenarios/corte-de-energia -H 'content-type: application/json' -d '{"device_id": "ups-norte-01"}'
```

El mapa de registros Modbus y los mensajes de cada protocolo están en los docstrings de
`ups_modbus.py`, `barrier_ws.py` y `camera_http.py`.
