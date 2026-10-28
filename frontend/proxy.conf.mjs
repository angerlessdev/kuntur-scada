// Development proxy: the SPA calls /api on its own origin, as it does behind nginx in production.
// KUNTUR_API_URL points it at another backend (default: the API on this machine, port 8000).
const target = process.env.KUNTUR_API_URL ?? 'http://127.0.0.1:8000';

export default {
  '/api': { target, secure: false, ws: true, changeOrigin: false },
};
