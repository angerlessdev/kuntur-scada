# 0003. Un cliente Modbus TCP propio, validado contra pymodbus

- Estado: aceptada
- Fecha: 2026-10-28

## Contexto

Un SCADA no solo debe saber que un equipo no responde, sino **por qué**: no es lo mismo una conexión
rechazada (el equipo está pero su servicio no) que un tiempo agotado (el equipo o la ruta se colgaron).
El cliente de pymodbus, al fallar la conexión, devuelve `False` y escribe el motivo en su propio log:
la causa se pierde.

## Decisión

Escribir un cliente mínimo, fiel a la especificación (Modbus Application Protocol v1.1b3 y la guía de
Modbus sobre TCP/IP), con solo las funciones que la plataforma usa: 4 (leer registros de entrada) y 6
(escribir un registro). Una conexión por petición. El simulador sigue usando el servidor de pymodbus.

## Consecuencias

- Cada falla de red llega con su causa a la taxonomía común, igual que en los drivers WebSocket y HTTP.
- Las pruebas de integración leen el UPS simulado con el cliente propio y comparan registro por
  registro con lo que pymodbus sirve: dos implementaciones independientes que tienen que coincidir.
- Es código propio que mantener; está acotado a dos funciones y ~80 líneas.
