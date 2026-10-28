"""Errors as RFC 9457 problem details (``application/problem+json``).

Each domain error has one status and one stable ``type``, so a client can branch on it without parsing
text. An unexpected error answers a generic 500 and never includes the exception's text: that would
leak internals. It is logged instead.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from kuntur.domain.errors import (
    AuthenticationError,
    CommandNotAllowedError,
    DomainError,
    DomainValidationError,
    InvalidTransitionError,
    NotFoundError,
    PermissionDeniedError,
    TooManyAttemptsError,
)

logger = logging.getLogger(__name__)

MEDIA_TYPE = "application/problem+json"

_DOMAIN: dict[type[DomainError], tuple[int, str, str]] = {
    NotFoundError: (404, "not-found", "Recurso no encontrado"),
    AuthenticationError: (401, "unauthenticated", "Autenticación requerida"),
    PermissionDeniedError: (403, "forbidden", "Tu rol no permite esta operación"),
    CommandNotAllowedError: (409, "command-not-allowed", "El equipo no admite esa orden"),
    InvalidTransitionError: (409, "invalid-transition", "Cambio de estado no permitido"),
    DomainValidationError: (422, "invalid-data", "Datos inválidos"),
    TooManyAttemptsError: (429, "too-many-attempts", "Demasiados intentos fallidos"),
}
_HTTP_TITLES = {404: "Recurso no encontrado", 405: "Método no permitido", 413: "Cuerpo demasiado grande"}


class BodyTooLarge(Exception):  # noqa: N818 - raised by the body-limit middleware while reading
    """The request body went over the limit while it was being read."""


def problem(
    status: int, slug: str, title: str, detail: str | None, instance: str, **extra: Any
) -> JSONResponse:
    body: dict[str, Any] = {"type": f"urn:kuntur:problem:{slug}", "title": title, "status": status}
    if detail:
        body["detail"] = detail
    body["instance"] = instance
    body.update(extra)
    return JSONResponse(body, status_code=status, media_type=MEDIA_TYPE)


def _domain_error(request: Request, exc: Exception) -> JSONResponse:
    for kind in type(exc).__mro__:
        if kind in _DOMAIN:
            status, slug, title = _DOMAIN[kind]
            break
    else:
        status, slug, title = 400, "domain-error", "Operación rechazada"
    response = problem(status, slug, title, str(exc), request.url.path)
    if isinstance(exc, AuthenticationError):
        response.headers["WWW-Authenticate"] = "Bearer"
    if isinstance(exc, TooManyAttemptsError):
        response.headers["Retry-After"] = str(exc.retry_after_s)
    return response


def _validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101 - registered for this type only
    errors = [
        {"loc": list(error.get("loc", ())), "msg": error.get("msg", ""), "type": error.get("type", "")}
        for error in exc.errors()
    ]
    return problem(422, "validation", "La petición no es válida", None, request.url.path, errors=errors)


def _http_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)  # noqa: S101 - registered for this type only
    title = _HTTP_TITLES.get(exc.status_code, "Error en la petición")
    response = problem(exc.status_code, f"http-{exc.status_code}", title, None, request.url.path)
    for name, value in (exc.headers or {}).items():
        response.headers[name] = value
    return response


def _too_large(request: Request, exc: Exception) -> JSONResponse:
    return problem(413, "http-413", _HTTP_TITLES[413], None, request.url.path)


def _unexpected(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
    return problem(500, "internal", "Error interno", None, request.url.path)


def install(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(BodyTooLarge, _too_large)
    app.add_exception_handler(Exception, _unexpected)
