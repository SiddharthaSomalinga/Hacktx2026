"""Host answers to requests (FR-36, 37, D20)."""

from __future__ import annotations

from app.domain.types import RequestStatus
from app.services.context import Context


class RequestService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def accept(self, user_id: str, request_id: str) -> str:
        raise NotImplementedError

    def decline(self, user_id: str, request_id: str, mute: bool) -> RequestStatus:
        raise NotImplementedError
