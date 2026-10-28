"""IP cameras over HTTP with Digest authentication. One app serves every camera, by path::

GET  /cameras/{id}/status  -> 200 {"device_time": "...", "uptime_s": 86400, "recording": true,
                                   "storage_free_pct": 40.1, "temperature_c": 42.3}
                              503 while it reboots
POST /cameras/{id}/reboot  -> 202 {"detail": "Reinicio en curso"}, 409 if already rebooting
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request

from kuntur_sim.digest import DigestResult, DigestVerifier
from kuntur_sim.models import CameraModel, CommandRejected


def create_camera_app(
    cameras: Mapping[str, CameraModel], verifier: DigestVerifier, clock: Callable[[], datetime]
) -> FastAPI:
    app = FastAPI(title="Kuntur camera simulator", docs_url=None, redoc_url=None, openapi_url=None)

    async def authenticate(request: Request) -> None:
        uri = request.url.path + (f"?{request.url.query}" if request.url.query else "")
        result = verifier.verify(request.headers.get("authorization"), request.method, uri)
        if result is not DigestResult.OK:
            challenge = verifier.challenge(stale=result is DigestResult.STALE)
            raise HTTPException(401, "Autenticación requerida", headers={"WWW-Authenticate": challenge})

    def camera(camera_id: str) -> CameraModel:
        model = cameras.get(camera_id)
        if model is None:
            raise HTTPException(404, "Cámara desconocida")
        return model

    @app.get("/cameras/{camera_id}/status", dependencies=[Depends(authenticate)])
    async def status(camera_id: str) -> dict[str, Any]:
        model = camera(camera_id)
        if model.rebooting:
            raise HTTPException(503, "Reiniciando")
        return {
            "device_time": model.device_time(clock()).isoformat(),
            "uptime_s": round(model.uptime_s),
            "recording": model.recording,
            "storage_free_pct": round(model.storage_free_pct, 1),
            "temperature_c": round(model.temperature_c, 1),
        }

    @app.post("/cameras/{camera_id}/reboot", status_code=202, dependencies=[Depends(authenticate)])
    async def reboot(camera_id: str) -> dict[str, str]:
        try:
            return {"detail": camera(camera_id).reboot()}
        except CommandRejected as exc:
            raise HTTPException(409, str(exc)) from exc

    return app
