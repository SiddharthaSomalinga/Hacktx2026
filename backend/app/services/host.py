"""Host sessions (FR-20..28, D17, D18, D20, D23, D24)."""

from __future__ import annotations

import uuid
from dataclasses import replace

from app.domain.lifecycle import confirm_due
from app.domain.seat_engine import human_present_now
from app.domain.types import EndReason, HostSession, Topic
from app.services.context import Context
from app.services.errors import conflict, not_found
from app.services.facts import Facts
from app.services.lifecycle import LifecycleService
from app.services.ports import Conflict, Lock, Tx
from app.services.topics import TopicsService
from app.services.views import ConfirmView, InboxItemView


def _live_session(tx: Tx, user_id: str, lock: Lock = Lock.NONE) -> HostSession:
    session = tx.live_session_for_user(user_id, lock)
    if session is None:
        raise conflict("not_linked", "Link to your seat first")
    return session


class HostService:
    def __init__(self, ctx: Context, lifecycle: LifecycleService, topics: TopicsService) -> None:
        self._ctx = ctx
        self._lifecycle = lifecycle
        self._topics = topics

    def _refresh(self, user_id: str) -> None:
        with self._ctx.repo.read() as tx:
            session = tx.live_session_for_user(user_id)
        if session is not None:
            self._lifecycle.advance_session(session.id)

    def link(self, user_id: str, seat_id: str) -> str:
        """FR-21/22: linking creates the session (D17); one role at a time (FR-50)."""
        self._refresh(user_id)
        with self._ctx.repo.read() as tx:
            for other in tx.live_sessions_for_seats([seat_id]):
                self._lifecycle.advance_session(other.id)  # a departed host's session may be over
        now = self._ctx.clock.now()
        with self._ctx.repo.tx() as tx:
            facts = Facts(tx, now, self._ctx.timers)
            seat = facts.seat(seat_id)
            if seat is None:
                raise not_found("seat_not_found", f"No seat {seat_id!r}")
            if tx.active_search_for_user(user_id) or tx.active_match_for_seeker(user_id):
                raise conflict("already_searching", "Finish or cancel your search first")
            existing = tx.live_session_for_user(user_id, Lock.WAIT)
            if existing is not None:
                if existing.seat_id == seat_id:
                    return existing.id  # re-opening the seat link is idempotent
                raise conflict("already_hosting", "Turn off host mode before linking another seat")
            state = facts.seat_state(seat)
            if (
                seat.is_simulated
                or state is None
                or not human_present_now(state, now, self._ctx.timers)
            ):
                raise conflict("seat_not_occupied", "Sit down first: the seat doesn't read you yet")
            if tx.live_sessions_for_seats([seat_id]):
                raise conflict("seat_taken", "Someone else is hosting from this seat")
            session = HostSession(
                id=str(uuid.uuid4()),
                user_id=user_id,
                seat_id=seat_id,
                topic_raw=None,
                course_code=None,
                subject=None,
                keywords=(),
                about_me=None,
                open=True,
                muted=False,
                started_at=now,
                expires_at=now + self._ctx.timers.session_max,
                ended_at=None,
                end_reason=None,
                confirm_notified_at=None,
            )
            try:
                tx.insert_session(session)
            except Conflict as exc:
                raise conflict("already_hosting", "You're already hosting") from exc
            return session.id

    def set_topic(self, user_id: str, topic_raw: str, about_me: str | None) -> Topic:
        with self._ctx.repo.read() as tx:
            _live_session(tx, user_id)
        topic = self._topics.normalize(topic_raw)
        with self._ctx.repo.tx() as tx:
            session = _live_session(tx, user_id, Lock.WAIT)
            tx.update_session(
                replace(
                    session,
                    topic_raw=topic_raw,
                    course_code=topic.course_code,
                    subject=topic.subject,
                    keywords=topic.keywords,
                    label=topic.label,
                    about_me=about_me,
                )
            )
        return topic

    def toggle(self, user_id: str, open_: bool) -> bool:
        """`open: false` ends the session (D17). `open: true` only reports a live session."""
        self._refresh(user_id)
        if open_:
            with self._ctx.repo.read() as tx:
                _live_session(tx, user_id)
            return True
        now = self._ctx.clock.now()
        with self._ctx.repo.tx() as tx:
            session = tx.live_session_for_user(user_id, Lock.WAIT)
            if session is None:
                return False
            searches = self._lifecycle.end_session(tx, session, EndReason.TOGGLED_OFF, now)
        for search_id in searches:
            self._lifecycle.advance_search(search_id)
        return False

    def mute(self, user_id: str, muted: bool) -> bool:
        with self._ctx.repo.tx() as tx:
            session = _live_session(tx, user_id, Lock.WAIT)
            tx.update_session(replace(session, muted=muted))
            pending = [r.search_id for r in tx.pending_requests_for_session(session.id)]
        for search_id in pending:
            self._lifecycle.advance_search(
                search_id
            )  # FR-25: a muted host's pending requests move on
        return muted

    def confirm(self, user_id: str) -> ConfirmView:
        """FR-27 (D24): renew only while the confirmation is due."""
        self._refresh(user_id)
        now = self._ctx.clock.now()
        with self._ctx.repo.tx() as tx:
            session = _live_session(tx, user_id, Lock.WAIT)
            if not confirm_due(session, now, self._ctx.timers):
                raise conflict("confirm_not_due", "No confirmation is needed right now")
            renewed = replace(session, expires_at=now + self._ctx.timers.session_max)
            tx.update_session(renewed)
        return ConfirmView(renewed.expires_at)

    def inbox(self, user_id: str) -> list[InboxItemView]:
        self._refresh(user_id)
        with self._ctx.repo.read() as tx:
            session = _live_session(tx, user_id)
            searches = [r.search_id for r in tx.pending_requests_for_session(session.id)]
        for search_id in searches:
            self._lifecycle.advance_search(search_id)  # expire anything already due
        now = self._ctx.clock.now()
        with self._ctx.repo.read() as tx:
            session = _live_session(tx, user_id)
            facts = Facts(tx, now, self._ctx.timers)
            seat = facts.seat(session.seat_id)
            assert seat is not None
            table_label = facts.table_of(seat).label
            items: list[InboxItemView] = []
            for request in tx.pending_requests_for_session(session.id):
                search = tx.search(request.search_id)
                assert search is not None
                seeker = tx.user(search.seeker_id)
                assert seeker is not None
                left = max(0, int((request.expires_at - now).total_seconds()))
                items.append(
                    InboxItemView(
                        request.id, seeker.first_name, seeker.major, search.label, table_label, left
                    )
                )
            return items
