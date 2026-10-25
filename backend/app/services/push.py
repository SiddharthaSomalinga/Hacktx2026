"""Push subscriptions and the outbox sender (FR-51..53, D30)."""

from __future__ import annotations

from app.services.context import Context


class PushService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def vapid_public_key(self) -> str:
        return self._ctx.vapid_public_key

    def subscribe(self, user_id: str, endpoint: str, p256dh: str, auth: str) -> None:
        raise NotImplementedError

    def unsubscribe(self, user_id: str, endpoint: str) -> None:
        raise NotImplementedError

    def drain(self, limit: int = 50) -> int:
        raise NotImplementedError
