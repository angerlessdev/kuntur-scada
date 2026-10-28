"""FastAPI dependencies: the assembled application and the authenticated actor."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from kuntur.bootstrap import Application
from kuntur.domain.errors import AuthenticationError
from kuntur.domain.security import Actor

_bearer = HTTPBearer(auto_error=False, description="El token que entrega POST /api/v1/auth/token")


def get_application(request: Request) -> Application:
    application: Application = request.app.state.application
    return application


App = Annotated[Application, Depends(get_application)]


async def current_actor(
    application: App,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> Actor:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Falta el token de sesión")
    return await run_in_threadpool(application.resolve_actor, credentials.credentials)


CurrentActor = Annotated[Actor, Depends(current_actor)]
