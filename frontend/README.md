# Consola web de Kuntur SCADA

Angular 21 (componentes standalone, signals, sin zone.js). Sigue la filosofía de las pantallas de alto
desempeño (ISA-101): lo normal se ve gris y tranquilo; el color se reserva para lo que pide atención, y
cada estado lleva además una forma y una palabra.

```bash
npm ci
KUNTUR_API_URL=http://127.0.0.1:8000 npm start   # http://localhost:4200, con /api apuntando a la API
npm test -- --watch=false                       # pruebas unitarias (Vitest)
npm run build                                   # producción, en dist/kuntur-web
```

En producción la sirve nginx (`Dockerfile`, `nginx.conf`), que también hace de proxy de `/api` y del
canal en vivo: el navegador habla con un solo origen y la política de seguridad de contenido no
necesita abrir otros.
