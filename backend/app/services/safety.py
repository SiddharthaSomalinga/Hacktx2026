"""Blocking and reporting (FR-45). Blocks apply in both directions at query time."""

from __future__ import annotations

from app.services.context import Context
from app.services.errors import DomainError, not_found


class SafetyService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def _check(self, user_id: str, other_id: str) -> None:
        if other_id == user_id:
            raise DomainError("validation_error", "You can't block or report yourself", 422)

    def block(self, user_id: str, other_id: str) -> None:
        self._check(user_id, other_id)
        with self._ctx.repo.tx() as tx:
            if tx.user(other_id) is None:
                raise not_found("unknown_user", "No such user")
            tx.insert_block(user_id, other_id)

    def report(self, user_id: str, other_id: str, reason: str) -> None:
        """A report also blocks (FR-45)."""
        self._check(user_id, other_id)
        now = self._ctx.clock.now()
        with self._ctx.repo.tx() as tx:
            if tx.user(other_id) is None:
                raise not_found("unknown_user", "No such user")
            tx.insert_report(user_id, other_id, reason, now)
            tx.insert_block(user_id, other_id)
