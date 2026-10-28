# 0004. SQL Server con SQLAlchemy Core, sin ORM

- Estado: aceptada
- Fecha: 2026-10-28

## Contexto

Las entidades del dominio son dataclasses con reglas propias. Un ORM las acoplaría a la base (sesiones,
estados de identidad, carga perezosa) y escondería el SQL que importa en las lecturas de series de tiempo.

## Decisión

- SQLAlchemy Core con mapeo explícito fila ↔ entidad, en los dos sentidos.
- Migraciones con Alembic, empaquetadas con la aplicación (`kuntur-db upgrade`), y una prueba que
  compara las migraciones con el esquema que consulta el código.
- Lecturas agrupadas (índice *clustered*) por equipo y hora: la última lectura y la historia de un equipo
  son recorridos de rango. Las métricas van en JSON (`NVARCHAR(MAX)` con `ISJSON`), porque cada tipo de
  equipo tiene las suyas; el promedio de temperatura usa `JSON_VALUE`.
- La base se crea con `READ_COMMITTED_SNAPSHOT`: las pantallas leen sin bloquear al colector.
- Horas en `DATETIME2(6)` en UTC; un `datetime` sin zona horaria se rechaza.

## Consecuencias

- Las invariantes del dominio también viven en la base: una alerta activa por equipo y código (índice
  único filtrado) y `CHECK` que mantienen coherentes estado y fechas.
- pymssql redondea los parámetros `datetime` al milisegundo; por eso viajan como texto ISO 8601 y la
  ida y vuelta conserva los microsegundos. Una prueba de contrato lo cubre.
- Las mismas pruebas de contrato corren contra la unidad de trabajo en memoria y contra un SQL Server
  2022 real (Testcontainers): las pruebas rápidas no pueden mentir sobre la base.
