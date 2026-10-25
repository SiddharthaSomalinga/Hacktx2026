"""Blocking and reporting (FR-45). Blocks apply in both directions at query time."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.context import Context
from app.services.errors import DomainError, forbidden, not_found
from app.services.ports import Tx


@dataclass(frozen=True)
class Other:
    """The person to block, named directly or through a shared request or match (D53).

    The client never learns the other person's user id, so it names the request or match it is
    looking at; the server resolves who is on the other side.
    """

    user_id: str | None = None
    request_id: str | None = None
    match_id: str | None = None


def _other_side(tx: Tx, user_id: str, seeker_id: str, host_session_id: str) -> str | None:
    session = tx.session(host_session_id)
    host_id = session.user_id if session else None
    if user_id == seeker_id:
        return host_id
    if user_id == host_id:
        return seeker_id
    return None


class SafetyService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def _resolve(self, tx: Tx, user_id: str, other: Other) -> str:
        if other.request_id is not None:
            request = tx.request(other.request_id)
            if request is None:
                raise not_found("request_not_found", "No such request")
            found = _other_side(tx, user_id, request.seeker_id, request.host_session_id)
            if found is None:
                raise forbidden("not_your_request", "You're not part of this request")
            return found
        if other.match_id is not None:
            match = tx.match(other.match_id)
            if match is None:
                raise not_found("match_not_found", "No such match")
            found = _other_side(tx, user_id, match.seeker_id, match.host_session_id)
            if found is None:
                raise forbidden("not_in_match", "You're not part of this match")
            return found
        assert other.user_id is not None
        if other.user_id == user_id:
            raise DomainError("validation_error", "You can't block or report yourself", 422)
        if tx.user(other.user_id) is None:
            raise not_found("unknown_user", "No such user")
        return other.user_id

    def block(self, user_id: str, other: Other) -> None:
        with self._ctx.repo.tx() as tx:
            tx.insert_block(user_id, self._resolve(tx, user_id, other))

    def report(self, user_id: str, other: Other, reason: str) -> None:
        """A report also blocks (FR-45)."""
        now = self._ctx.clock.now()
        with self._ctx.repo.tx() as tx:
            other_id = self._resolve(tx, user_id, other)
            tx.insert_report(user_id, other_id, reason, now)
            tx.insert_block(user_id, other_id)
