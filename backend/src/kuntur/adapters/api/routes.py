"""HTTP endpoints. Each one checks who is calling, runs one use case and maps the result to a DTO.

Reads are plain ``def`` (FastAPI runs them in its thread pool, where blocking database I/O belongs);
commands are ``async`` because the use case awaits the device.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.concurrency import run_in_threadpool
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import AwareDatetime

from kuntur.adapters.api.dependencies import App, CurrentActor
from kuntur.adapters.api.schemas import (
    AlertOut,
    CommandIn,
    CommandOut,
    DeviceOverviewOut,
    ExplanationOut,
    LoginIn,
    MeOut,
    ReadingOut,
    TokenOut,
)
from kuntur.domain.alerts import AlertState

api = APIRouter(prefix="/api/v1")
ops = APIRouter(tags=["operación"])

DeviceId = Annotated[str, Query(min_length=2, max_length=40, pattern=r"^[a-z0-9-]+$")]


@api.post("/auth/token", tags=["sesión"], summary="Inicia sesión y entrega un token de acceso")
def login(credentials: LoginIn, request: Request, application: App) -> TokenOut:
    origin = request.client.host if request.client else "desconocido"
    issued = application.authenticate(credentials.username, credentials.password, origin)
    return TokenOut(
        access_token=issued.token,
        expires_at=issued.expires_at,
        username=issued.actor.username,
        role=issued.actor.role,
    )


@api.get("/auth/me", tags=["sesión"], summary="Quién es el usuario de la sesión")
def me(actor: CurrentActor) -> MeOut:
    return MeOut(username=actor.username, role=actor.role)


@api.get("/devices", tags=["flota"], summary="La flota activa con su salud, alertas y vida útil")
def devices(actor: CurrentActor, application: App) -> list[DeviceOverviewOut]:
    return [DeviceOverviewOut.of(view) for view in application.queries.overview()]


@api.get("/devices/{device_id}", tags=["flota"], summary="Un equipo, con su salud y su fecha de reemplazo")
def device(device_id: str, actor: CurrentActor, application: App) -> DeviceOverviewOut:
    return DeviceOverviewOut.of(application.queries.device(device_id))


@api.get("/devices/{device_id}/readings", tags=["flota"], summary="Lecturas de un equipo")
def readings(
    device_id: str,
    actor: CurrentActor,
    application: App,
    since: Annotated[
        AwareDatetime | None, Query(description="Desde cuándo (ISO 8601 con zona); sin él, las últimas")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
) -> list[ReadingOut]:
    found = application.queries.readings(device_id, since, limit)
    return [ReadingOut.of(reading) for reading in found]


@api.get("/alerts", tags=["alertas"], summary="Alertas, de la más reciente a la más antigua")
def alerts(
    actor: CurrentActor,
    application: App,
    state: AlertState | None = None,
    device_id: DeviceId | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AlertOut]:
    return [
        AlertOut.of(alert)
        for alert in application.queries.alerts(state=state, device_id=device_id, limit=limit)
    ]


@api.get("/alerts/{alert_id}", tags=["alertas"], summary="Una alerta")
def alert(alert_id: str, actor: CurrentActor, application: App) -> AlertOut:
    return AlertOut.of(application.queries.alert(alert_id))


@api.get(
    "/alerts/{alert_id}/explanation",
    tags=["alertas"],
    summary="Qué pasa, por qué probablemente pasa y qué revisar primero (Claude o la plantilla)",
)
async def explanation(alert_id: str, actor: CurrentActor, application: App) -> ExplanationOut:
    return ExplanationOut.of(await application.explain(alert_id))


@api.post(
    "/devices/{device_id}/commands",
    tags=["control"],
    status_code=status.HTTP_201_CREATED,
    summary="Envía una orden a un equipo (solo OPERATOR); queda auditada aunque el equipo no responda",
)
async def send_command(device_id: str, order: CommandIn, actor: CurrentActor, application: App) -> CommandOut:
    return CommandOut.of(await application.issue(actor, device_id, order.kind))


@api.get("/commands", tags=["control"], summary="Auditoría de órdenes, de la más reciente a la más antigua")
def commands(
    actor: CurrentActor,
    application: App,
    device_id: DeviceId | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[CommandOut]:
    return [
        CommandOut.of(command) for command in application.queries.commands(device_id=device_id, limit=limit)
    ]


@ops.get("/healthz", summary="El proceso está vivo")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@ops.get(
    "/readyz", summary="La base de datos responde", responses={503: {"description": "Sin base de datos"}}
)
async def readyz(application: App, response: Response) -> dict[str, str]:
    def probe() -> None:
        with application.uow_factory() as uow:
            uow.devices.get("readyz-probe")

    try:
        await run_in_threadpool(probe)
    except Exception:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "unavailable"}
    return {"status": "ready"}


@ops.get("/metrics", summary="Métricas de Prometheus", include_in_schema=False)
def metrics(application: App) -> Response:
    return Response(generate_latest(application.metrics.registry), media_type=CONTENT_TYPE_LATEST)
