"""Occupancy history (FR-49, D31)."""

from __future__ import annotations

from datetime import datetime

from app.services.context import Context


class HistoryService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def history(self, building_id: str) -> list[tuple[datetime, float]]:
        raise NotImplementedError
