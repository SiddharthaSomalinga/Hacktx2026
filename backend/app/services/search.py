"""Searches and the request cascade (FR-29..35, D15, D19, D22)."""

from __future__ import annotations

from app.domain.types import Group, SearchStatus
from app.services.context import Context
from app.services.views import SearchStatusView, SearchView


class SearchService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def create(self, user_id: str, topic_raw: str, group: Group | None) -> SearchView:
        raise NotImplementedError

    def join(self, user_id: str, search_id: str) -> SearchStatusView:
        raise NotImplementedError

    def status(self, user_id: str, search_id: str) -> SearchStatusView:
        raise NotImplementedError

    def cancel(self, user_id: str, search_id: str) -> SearchStatus:
        raise NotImplementedError
