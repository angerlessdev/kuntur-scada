"""Builds the FastAPI app around an assembled ``Application``."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from kuntur import __version__
from kuntur.adapters.api import problems, routes, websocket
from kuntur.adapters.api.middleware import BodyLimitMiddleware, SecurityHeadersMiddleware
from kuntur.bootstrap import Application


def create_api(application: Application) -> FastAPI:
    settings = application.settings

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await application.start()
        try:
            yield
        finally:
            await application.stop()

    app = FastAPI(
        title="Kuntur SCADA",
        version=__version__,
        summary="Supervisión y control de equipos de campo, con alertas confirmadas y auditadas.",
        lifespan=lifespan,
        docs_url="/docs" if settings.expose_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.expose_docs else None,
    )
    app.state.application = application
    problems.install(app)
    app.include_router(routes.api)
    app.include_router(routes.ops)
    app.include_router(websocket.router)
    # Added last runs first: the body limit sees the request before anything else
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(BodyLimitMiddleware)
    return app
