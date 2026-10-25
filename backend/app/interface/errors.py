"""Every failure leaves the API as `{"error": code, "message": sentence}` (REQUIREMENTS §7)."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.services.errors import DomainError

log = logging.getLogger("ghostseats.errors")


def _body(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": code, "message": message}, status_code=status)


def install(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return _body(exc.code, exc.message, exc.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        where = ".".join(str(p) for p in first.get("loc", ()) if p != "body")
        detail = first.get("msg", "Invalid request")
        return _body("validation_error", f"{where}: {detail}" if where else str(detail), 422)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "http_error")
        return _body(code, str(exc.detail), exc.status_code)

    @app.exception_handler(NotImplementedError)
    async def not_implemented(request: Request, _: NotImplementedError) -> JSONResponse:
        return _body("not_implemented", f"{request.url.path} is not implemented yet", 501)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return _body("internal_error", "Something went wrong on our side", 500)
