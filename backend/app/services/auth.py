"""Demo accounts and the "who am I" view (FR-14..16, D9)."""

from __future__ import annotations

from app.domain.types import HostVisibility, User
from app.services.context import Context
from app.services.errors import not_found
from app.services.facts import Facts
from app.services.lifecycle import LifecycleService
from app.services.views import HostStatusView, MeView


class AuthService:
    def __init__(self, ctx: Context, lifecycle: LifecycleService) -> None:
        self._ctx = ctx
        self._lifecycle = lifecycle

    def demo_users(self) -> list[User]:
        with self._ctx.repo.read() as tx:
            return tx.demo_users()

    def login(self, user_id: str) -> User:
        with self._ctx.repo.read() as tx:
            user = tx.user(user_id)
        if user is None or not user.is_demo:
            raise not_found("unknown_user", "Pick one of the demo users")
        return user

    def user(self, user_id: str) -> User | None:
        with self._ctx.repo.read() as tx:
            return tx.user(user_id)

    def me(self, user_id: str | None) -> MeView:
        if user_id is None:
            return MeView(None, None, None, None)
        with self._ctx.repo.read() as tx:
            session = tx.live_session_for_user(user_id)
        if session is not None:
            self._lifecycle.advance_session(session.id)  # status shown must be current
        now = self._ctx.clock.now()
        with self._ctx.repo.read() as tx:
            user = tx.user(user_id)
            if user is None:
                return MeView(None, None, None, None)
            session = tx.live_session_for_user(user_id)
            host = None
            match = tx.active_match_for_seeker(user_id)
            if session is not None:
                visibility, reason = Facts(tx, now, self._ctx.timers).host_status(session)
                if visibility is not HostVisibility.ENDED:
                    host = HostStatusView(
                        session.id,
                        session.seat_id,
                        session.label,
                        session.muted,
                        visibility,
                        reason,
                    )
                match = match or tx.active_match_for_session(session.id)
            search = tx.active_search_for_user(user_id)
            return MeView(user, host, search.id if search else None, match.id if match else None)
