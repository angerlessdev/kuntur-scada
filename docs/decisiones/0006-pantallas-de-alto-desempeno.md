# 0006. Pantallas de alto desempeño (ISA-101)

- Estado: aceptada
- Fecha: 2026-10-28

## Contexto

En una sala de control la pantalla se mira durante todo un turno. Si todo es colorido, lo anormal no
destaca; si el color es lo único que distingue un estado, una persona daltónica pierde información.

## Decisión

- Fondo gris tranquilo para lo normal; el color se reserva para lo que pide atención: ámbar para
  advertencia y degradado, rojo para crítico y sin comunicación.
- Cada estado tiene también una **forma** (rombo crítico, triángulo advertencia, anillo punteado sin datos)
  y una **palabra**.
- Indicadores analógicos con la banda normal y el límite de alarma, solo donde una regla del backend
  vigila esa variable y con la severidad de esa regla: ningún límite inventado en la interfaz.
- Las tendencias muestran la línea donde salta la alerta y la línea donde se apaga, para que la
  histéresis se vea.
- Tipografía Barlow, inspirada en la señalética vial y las placas de California, pensada para leerse
  rápido y a distancia. Va empaquetada con la aplicación: las redes de las salas de control suelen
  estar aisladas de internet.

## Consecuencias

- Una pantalla sin problemas se ve aburrida, y está bien: cuando aparece color, significa algo.
- Las pruebas unitarias de la consola verifican la forma y la palabra además del color, que un estado
  no se repita como alerta y que ningún indicador invente un límite.
