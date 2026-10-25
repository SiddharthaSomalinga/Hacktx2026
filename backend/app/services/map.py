"""Seat map snapshots and recommendations (FR-8..13, D21, D32)."""

from __future__ import annotations

from app.services.context import Context
from app.services.views import BuildingFullView, Cached, RecommendationView


class MapService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def buildings(self) -> Cached:
        raise NotImplementedError

    def building(self, building_id: str) -> Cached:
        raise NotImplementedError

    def recommend(
        self, building_id: str, floor: int | None, table_id: str | None
    ) -> RecommendationView | BuildingFullView:
        raise NotImplementedError
