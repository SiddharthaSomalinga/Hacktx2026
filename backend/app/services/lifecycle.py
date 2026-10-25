"""Applies the domain's transition decisions under row locks (NFR-2, D29).

Host sessions, searches and matches affect each other: a host leaving skips pending requests,
which advances searches, which sends new requests. This service owns all three so the chain
is handled in one place. Every method is safe to call at any time and from any trigger
(a read, an ingest, a scheduler tick): if nothing is due, nothing changes.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from app.domain import notifications as notify
from app.domain.lifecycle import (
    EndSession,
    Exhaust,
    MatchStep,
    PendingStep,
    SendTo,
    advance_host_session,
    advance_match,
    needs_send,
    next_hop,
    pending_step,
)
from app.domain.matching import can_still_receive, group_of, rank
from app.domain.types import (
    EndReason,
    Group,
    HostSession,
    HostVisibility,
    MatchStatus,
    OutboxMessage,
    RequestStatus,
    Search,
    SearchStatus,
    Seat,
    StudyRequest,
    Timers,
    Topic,
)
from app.services.context import Context
from app.services.facts import Facts
from app.services.ports import Lock, Tx

log = logging.getLogger("ghostseats.lifecycle")

HOUR = timedelta(hours=1)


@dataclass(frozen=True)
class Candidate:
    """A findable host as seen by one search (also satisfies the HostTopic port)."""

    session: HostSession
    seat: Seat
    group: Group
    major: str | None = None  # the host's major, filled in only for the AI calls (D43)

    @property
    def id(self) -> str:
        return self.session.id

    @property
    def topic(self) -> Topic:
        s = self.session
        return Topic(s.course_code, s.subject or "", s.keywords, s.label or "", self.major)

    @property
    def about_me(self) -> str | None:
        return self.session.about_me


def topic_of(search: Search, major: str | None = None) -> Topic:
    return Topic(search.course_code, search.subject, search.keywords, search.label, major)


def major_of(tx: Tx, user_id: str) -> str | None:
    user = tx.user(user_id)
    return user.major if user else None


def findable_hosts(
    facts: Facts, seeker_id: str, course: str | None, subject: str
) -> list[Candidate]:
    """FR-24/29: findable hosts grouped against the seeker's topic, blocks applied both ways."""
    blocked = facts.tx.blocked_with(seeker_id)
    out: list[Candidate] = []
    for session in facts.tx.live_sessions():
        if session.user_id == seeker_id or session.user_id in blocked:
            continue
        group = group_of(course, subject, session.course_code, session.subject)
        if group is None:
            continue
        if facts.host_status(session)[0] is not HostVisibility.FINDABLE:
            continue
        seat = facts.seat(session.seat_id)
        assert seat is not None
        out.append(Candidate(session, seat, group))
    return out


class LifecycleService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    @property
    def _t(self) -> Timers:
        return self._ctx.timers

    def _facts(self, tx: Tx, now: datetime) -> Facts:
        return Facts(tx, now, self._ctx.timers)

    # --- host sessions -------------------------------------------------------

    def end_session(
        self, tx: Tx, session: HostSession, reason: EndReason, now: datetime
    ) -> list[str]:
        """End a live session inside `tx`. Returns search ids that need advancing afterwards."""
        tx.update_session(replace(session, ended_at=now, end_reason=reason))
        messages: list[OutboxMessage] = []
        if reason is not EndReason.TOGGLED_OFF:
            messages.append(notify.session_ended(session.user_id))
        match = tx.active_match_for_session(session.id)
        if match is not None:
            tx.update_match(replace(match, status=MatchStatus.CANCELLED))
            messages.append(notify.match_cancelled(match.seeker_id, match.id))
        tx.enqueue(messages, now)
        return [r.search_id for r in tx.pending_requests_for_session(session.id)]

    def advance_session(self, session_id: str, lock: Lock = Lock.WAIT) -> None:
        now = self._ctx.clock.now()
        with self._ctx.repo.tx() as tx:
            session = tx.session(session_id, lock)
            if session is None or not session.live:
                return
            facts = self._facts(tx, now)
            seat = facts.seat(session.seat_id)
            assert seat is not None
            step = advance_host_session(session, seat, facts.seat_state(seat), now, self._t)
            if isinstance(step, EndSession):
                searches = self.end_session(tx, session, step.reason, now)
            else:
                if step.notify_confirm:
                    tx.update_session(replace(session, confirm_notified_at=now))
                    tx.enqueue([notify.confirm_needed(session.user_id)], now)
                searches = [r.search_id for r in tx.pending_requests_for_session(session.id)]
            match = tx.active_match_for_session(session.id)
        for search_id in searches:
            self.advance_search(search_id)
        if match is not None:
            self.advance_match(match.id)

    # --- searches ------------------------------------------------------------

    def _settle_pending(self, search_id: str, now: datetime, lock: Lock) -> Search | None:
        """Expire or skip the pending request while one is due. Returns the search if it may
        need a new send, or None when there is nothing further to do."""
        while True:
            with self._ctx.repo.tx() as tx:
                search = tx.search(search_id, lock)
                if search is None or search.status is not SearchStatus.ACTIVE:
                    return None
                pending = tx.pending_request_for_search(search_id)
                if pending is None:
                    return search if needs_send(search, None) else None
                facts = self._facts(tx, now)
                visibility, reason = facts.host_status(tx.session(pending.host_session_id))
                step = pending_step(pending, can_still_receive(visibility, reason), now)
                if step is PendingStep.WAIT:
                    return None
                status = (
                    RequestStatus.EXPIRED if step is PendingStep.EXPIRE else RequestStatus.SKIPPED
                )
                tx.update_request(replace(pending, status=status))

    def advance_search(self, search_id: str, lock: Lock = Lock.WAIT) -> None:
        now = self._ctx.clock.now()
        search = self._settle_pending(search_id, now, lock)
        if search is None:
            return

        # Rank outside any lock: the AI call may take up to AI_TIMEOUT_S.
        with self._ctx.repo.read() as tx:
            candidates = [
                c
                for c in findable_hosts(
                    self._facts(tx, now), search.seeker_id, search.course_code, search.subject
                )
                if c.group is search.offered_group
                and (self._ctx.demo_hosts or not c.seat.is_simulated)  # FR-31, D56
            ]
            # D43: Muse ranks with each side's major; names never reach the model.
            seeker_topic = topic_of(search, major_of(tx, search.seeker_id))
            candidates = [replace(c, major=major_of(tx, c.session.user_id)) for c in candidates]
        scores = self._ctx.ai.rank_hosts(seeker_topic, candidates)
        ranked_ids = [s.id for s in rank((c.session for c in candidates), scores)]

        with self._ctx.repo.tx() as tx:
            search = tx.search(search_id, Lock.WAIT)
            if search is None or not needs_send(search, tx.pending_request_for_search(search_id)):
                return  # another trigger already acted
            facts = self._facts(tx, now)
            still = [
                sid
                for sid in ranked_ids
                if facts.host_status(tx.session(sid))[0] is HostVisibility.FINDABLE
            ]
            sent = tx.count_requests_since(search.seeker_id, now - HOUR)
            hop = next_hop(search, still, sent, self._t)
            if isinstance(hop, Exhaust):
                tx.update_search(replace(search, status=SearchStatus.EXHAUSTED))
                tx.enqueue([notify.search_exhausted(search.seeker_id, search.id)], now)
                return
            assert isinstance(hop, SendTo)
            host = tx.session(hop.session_id)
            assert host is not None
            seat = facts.seat(host.seat_id)
            assert seat is not None
            tx.insert_request(
                StudyRequest(
                    id=str(uuid.uuid4()),
                    search_id=search.id,
                    seeker_id=search.seeker_id,
                    host_session_id=host.id,
                    status=RequestStatus.PENDING,
                    created_at=now,
                    expires_at=now + self._t.request_timeout,
                )
            )
            tx.update_search(
                replace(search, tried_session_ids=(*search.tried_session_ids, host.id))
            )
            seeker = tx.user(search.seeker_id)
            assert seeker is not None
            tx.enqueue(
                [
                    notify.request_received(
                        host.user_id, seeker, search.label, facts.table_of(seat).label
                    )
                ],
                now,
            )

    # --- matches -------------------------------------------------------------

    def advance_match(self, match_id: str, lock: Lock = Lock.WAIT) -> None:
        now = self._ctx.clock.now()
        with self._ctx.repo.tx() as tx:
            match = tx.match(match_id, lock)
            if match is None or match.status is not MatchStatus.ACTIVE:
                return
            host = tx.session(match.host_session_id)
            assert host is not None
            facts = self._facts(tx, now)
            seat = facts.seat(host.seat_id)
            assert seat is not None
            step = advance_match(
                match, facts.seat_state(seat), now, self._t, host_simulated=seat.is_simulated
            )
            if step is MatchStep.KEEP:
                return
            if step is MatchStep.EXPIRE:
                tx.update_match(replace(match, status=MatchStatus.EXPIRED))
                messages = [
                    notify.match_expired(match.seeker_id, match.id),
                    notify.match_expired(host.user_id, match.id),
                ]
            else:
                tx.update_match(replace(match, status=MatchStatus.CANCELLED))
                messages = [
                    notify.match_cancelled(match.seeker_id, match.id),
                    notify.match_cancelled(host.user_id, match.id),
                ]
            tx.enqueue(messages, now)
