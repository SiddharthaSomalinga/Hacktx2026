"""Matches (FR-37..42, D18, D25)."""

from __future__ import annotations

from app.domain.types import MatchStatus
from app.services.context import Context
from app.services.views import MatchView


class MatchService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def view(self, user_id: str, match_id: str) -> MatchView:
        raise NotImplementedError

    def arrived(self, user_id: str, match_id: str) -> MatchStatus:
        raise NotImplementedError

    def cancel(self, user_id: str, match_id: str) -> MatchStatus:
        raise NotImplementedError
