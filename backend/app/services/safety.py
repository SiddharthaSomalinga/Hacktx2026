"""Blocking and reporting (FR-45)."""

from __future__ import annotations

from app.services.context import Context


class SafetyService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def block(self, user_id: str, other_id: str) -> None:
        raise NotImplementedError

    def report(self, user_id: str, other_id: str, reason: str) -> None:
        raise NotImplementedError
