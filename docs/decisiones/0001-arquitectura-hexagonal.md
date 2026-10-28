# 0001. Arquitectura hexagonal con un dominio sin dependencias

- Estado: aceptada
- Fecha: 2026-10-28

## Contexto

Una plataforma SCADA vive más que sus tecnologías: los equipos cambian de protocolo, la base de datos
la elige otra área y el proveedor de IA de hoy no será el de dentro de tres años. Las reglas que
deciden cuándo alarmar, en cambio, son el valor del sistema y tienen que poder probarse sin red ni base.

## Decisión

Separar el código en dominio, aplicación y adaptadores. El dominio son dataclasses y funciones puras;
la aplicación define puertos como `Protocol` de Python y los casos de uso solo hablan con ellos; los
adaptadores implementan esos puertos. Un único *composition root* (`kuntur.bootstrap`) conecta todo.

## Consecuencias

- Las reglas de alertas tienen pruebas unitarias y de propiedades (Hypothesis) que corren en
  milisegundos, y escenarios BDD en español que describen el comportamiento esperado.
- Cambiar SQL Server por otra base, o Claude por otro modelo, es escribir un adaptador; no se toca el
  dominio. Hay dos adaptadores reales de persistencia (SQL Server y memoria) que pasan el mismo
  contrato, y dos narradores (Claude y plantilla).
- Hay más archivos y más indirección que en un CRUD; es el precio de poder probar cada pieza aislada.
