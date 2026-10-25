"""Liveness and database reachability."""

from __future__ import annotations

from app.services.context import Context


class HealthService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def db_ok(self) -> bool:
        return self._ctx.repo.ping()
