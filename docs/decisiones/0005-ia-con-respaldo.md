# 0005. Explicaciones con Claude, siempre con una plantilla de respaldo

- Estado: aceptada
- Fecha: 2026-10-28

## Contexto

Ante una alerta, el operador necesita saber qué pasa, por qué probablemente pasa y qué revisar primero.
Un modelo de lenguaje lo explica bien con los datos del incidente, pero puede no estar disponible, tardar,
negarse o equivocarse. Y los datos vienen de los equipos: un texto de un equipo podría intentar dar
órdenes.

## Decisión

- El puerto `IncidentNarrator` tiene dos adaptadores: `ClaudeNarrator` (SDK oficial de Anthropic, Claude
  Opus 5.5 con esfuerzo bajo, porque el operador está esperando) y `TemplateNarrator`, determinista.
- La respuesta del modelo sigue un **esquema JSON** cuyo campo de orden solo admite las órdenes que ese
  equipo acepta; aun así se valida, y el caso de uso la vuelve a vigilar.
- Los datos del incidente viajan dentro de un bloque `<datos>` que el prompt declara como datos, nunca
  instrucciones.
- Cualquier falla (sin credenciales, tiempo agotado, rechazo, formato inválido) termina en la plantilla, y
  la pantalla dice quién escribió la explicación y por qué.
- Ante un rechazo de seguridad, el servidor reintenta en el modelo que Anthropic recomienda
  (`fallbacks: "default"`).

## Consecuencias

- La plataforma funciona completa sin clave de Anthropic.
- Las evaluaciones (11 casos, 7 calificadores) corren gratis contra la plantilla en cada CI; contra
  Claude solo con `--yes`, después de mostrar el costo estimado.
- Las pruebas usan el cliente real del SDK con un transporte simulado: se verifica la petición exacta
  (modelo, esfuerzo, `fallbacks`, esquema) sin red ni costo.
