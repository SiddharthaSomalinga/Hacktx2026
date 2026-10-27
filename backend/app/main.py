"""App factory: wires adapters into services and services into routes."""

from __future__ import annotations

import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import Settings, get_settings
from app.interface import errors
from app.interface.routes import (
    account,
    host,
    matches,
    public,
    push,
    readings,
    requests,
    safety,
    search,
)
from app.services.container import Services
from app.worker import Worker

log = logging.getLogger("ghostseats.http")


def create_app(settings: Settings, services: Services) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        worker = Worker(services, settings.scheduler_tick_s) if settings.worker_enabled else None
        if worker is not None:
            worker.start()
        try:
            yield
        finally:
            if worker is not None:
                worker.stop()

    app = FastAPI(
        title="Synapse API",
        version="1.1.0",
        description="Contract: documentation/REQUIREMENTS.md §7.",
        lifespan=lifespan,
    )
    app.state.services = services
    app.state.node_key = settings.node_key.get_secret_value()

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.secret_key.get_secret_value(),
        session_cookie="gs_session",
        same_site="lax",
        https_only=settings.cookie_secure,
    )

    @app.middleware("http")
    async def access_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - started) * 1000
        log.info(
            "%s %s %d %.1fms", request.method, request.url.path, response.status_code, elapsed_ms
        )
        return response

    errors.install(app)
    for module in (public, readings, account, search, host, requests, matches, safety, push):
        app.include_router(module.router)

    if settings.frontend_dist:
        _mount_frontend(app, Path(settings.frontend_dist))
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the built frontend from the same origin (D5); unknown non-API paths get index.html."""
    index = dist / "index.html"
    if not index.is_file():
        raise RuntimeError(f"FRONTEND_DIST has no index.html: {dist}")
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise StarletteHTTPException(404, "Not Found")  # API misses stay JSON, never the SPA
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index)


def build() -> FastAPI:
    """Entry point for uvicorn: `uvicorn app.main:build --factory`."""
    from app.wiring import build_services

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = get_settings()
    return create_app(settings, build_services(settings))
