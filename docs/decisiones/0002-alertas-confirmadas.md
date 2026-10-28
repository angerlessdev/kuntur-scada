# 0002. Alertas confirmadas: k de n, histéresis y tiempo mínimo

- Estado: aceptada
- Fecha: 2026-10-28

## Contexto

Una alarma que se dispara con un paquete perdido enseña al operador a ignorarla. En el campo, las redes
pierden lecturas sueltas, los valores rondan los límites y los enlaces parpadean. El objetivo no es
alarmar rápido, sino alarmar cuando hay algo real y no perder lo que sí lo es.

## Decisión

Cada regla es una estrategia (`AlertRule`) y el motor solo las orquesta:

- **Confirmación k de n:** «sin comunicación» exige 4 fallas en las últimas 5 lecturas y se apaga con 2
  respuestas seguidas.
- **Histéresis:** un umbral salta en un valor y se apaga en otro más seguro (la batería alerta sobre
  40 °C y se calma bajo 37 °C).
- **Tiempo mínimo** (un decorador, `FlapGuard`): una alerta dura al menos 30 s y no vuelve a saltar
  antes de 30 s de resuelta.
- **Caída esperada:** un reinicio ordenado abre una ventana de 90 s en la que el silencio del equipo no
  cuenta como pérdida de comunicación.

## Consecuencias

- La detección tarda unos segundos más que una regla ingenua; está medida en
  [calidad de las alertas](../calidad-de-alertas.md).
- Una lectura fallida sin confirmar se ve en amarillo: el operador ve el problema sin una alarma.
- Agregar una regla es una clase nueva; el motor no cambia. La base de datos respalda la invariante
  principal con un índice único filtrado: una sola alerta activa por equipo y código.
