"""Demo accounts and the "who am I" view (FR-14..16, D9)."""

from __future__ import annotations

from app.domain.types import User
from app.services.context import Context
from app.services.views import MeView


class AuthService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def demo_users(self) -> list[User]:
        raise NotImplementedError

    def login(self, user_id: str) -> User:
        raise NotImplementedError

    def user(self, user_id: str) -> User | None:
        raise NotImplementedError

    def me(self, user_id: str | None) -> MeView:
        raise NotImplementedError
