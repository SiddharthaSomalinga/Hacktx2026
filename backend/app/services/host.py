"""Host sessions (FR-20..28, D17, D18, D20, D23, D24)."""

from __future__ import annotations

from app.domain.types import Topic
from app.services.context import Context
from app.services.views import ConfirmView, InboxItemView


class HostService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def link(self, user_id: str, seat_id: str) -> str:
        raise NotImplementedError

    def set_topic(self, user_id: str, topic_raw: str, about_me: str | None) -> Topic:
        raise NotImplementedError

    def toggle(self, user_id: str, open_: bool) -> bool:
        raise NotImplementedError

    def mute(self, user_id: str, muted: bool) -> bool:
        raise NotImplementedError

    def confirm(self, user_id: str) -> ConfirmView:
        raise NotImplementedError

    def inbox(self, user_id: str) -> list[InboxItemView]:
        raise NotImplementedError
