"""Host answers to requests (FR-36, FR-37, D20, Q13)."""

from __future__ import annotations

import uuid
from dataclasses import replace

from app.domain import notifications as notify
from app.domain.geometry import nearest_seat
from app.domain.topic_rules import card_key_for
from app.domain.types import (
    HostSession,
    Match,
    MatchStatus,
    RequestStatus,
    SearchStatus,
    Seat,
    SeatChange,
    StudyRequest,
)
from app.services.context import Context
from app.services.errors import conflict, forbidden, not_found
from app.services.facts import Facts
from app.services.lifecycle import Candidate, LifecycleService, major_of, topic_of
from app.services.ports import Lock, Tx


def assign_seat(facts: Facts, host_seat: Seat) -> Seat | None:
    """FR-37: the open seat at the host's table nearest the host. If the table filled up since
    the request was sent, the nearest open seat on the floor (Q13); otherwise none."""
    at_table = nearest_seat(host_seat, facts.open_seats_at_table(host_seat))
    return at_table or nearest_seat(host_seat, facts.open_seats_on_floor(host_seat))


def _host_request(
    tx: Tx, user_id: str, request_id: str, lock: Lock = Lock.NONE
) -> tuple[StudyRequest, HostSession]:
    request = tx.request(request_id, lock)
    if request is None:
        raise not_found("request_not_found", "No such request")
    session = tx.session(request.host_session_id)
    if session is None or session.user_id != user_id:
        raise forbidden("not_your_request", "This request was sent to someone else")
    if request.status is not RequestStatus.PENDING:
        raise conflict("request_not_pending", "This request is no longer waiting for an answer")
    return request, session


class RequestService:
    def __init__(self, ctx: Context, lifecycle: LifecycleService) -> None:
        self._ctx = ctx
        self._lifecycle = lifecycle

    def accept(self, user_id: str, request_id: str) -> str:
        with self._ctx.repo.read() as tx:
            request, _ = _host_request(tx, user_id, request_id)
        self._lifecycle.advance_search(request.search_id)  # settles expiry before accepting

        with self._ctx.repo.read() as tx:
            request, session = _host_request(tx, user_id, request_id)
            search = tx.search(request.search_id)
            assert search is not None
            host_seat = tx.seat(session.seat_id)
            assert host_seat is not None
            seeker_major = major_of(tx, search.seeker_id)
            host_major = major_of(tx, session.user_id)
        # The icebreaker is generated before any lock is taken (≤ AI_TIMEOUT_S). D43: Muse
        # sees both majors, never names.
        icebreaker = self._ctx.ai.icebreaker(
            topic_of(search, seeker_major),
            Candidate(session, host_seat, search.offered_group, host_major).topic,
        )

        now = self._ctx.clock.now()
        with self._ctx.repo.tx() as tx:
            request, session = _host_request(tx, user_id, request_id, Lock.WAIT)
            if now >= request.expires_at:
                raise conflict("request_not_pending", "This request has expired")
            search = tx.search(request.search_id, Lock.WAIT)
            if search is None or search.status is not SearchStatus.ACTIVE:
                raise conflict("request_not_pending", "The seeker cancelled this search")
            if not session.live:
                raise conflict("not_linked", "Your host session has ended")
            facts = Facts(tx, now, self._ctx.timers)
            seat = facts.seat(session.seat_id)
            assert seat is not None
            assigned = assign_seat(facts, seat)
            match = Match(
                id=str(uuid.uuid4()),
                request_id=request.id,
                seeker_id=request.seeker_id,
                host_session_id=session.id,
                icebreaker=icebreaker,
                card_key=card_key_for(session.subject or search.subject),
                assigned_seat_id=assigned.id if assigned else None,
                status=MatchStatus.ACTIVE,
                created_at=now,
                expires_at=now + self._ctx.timers.match_timeout,
                arrived_at=None,
            )
            tx.insert_match(match)
            tx.update_request(replace(request, status=RequestStatus.ACCEPTED))
            tx.update_search(replace(search, status=SearchStatus.MATCHED))
            state = tx.lock_seat_state(seat.id)
            if state is not None:
                blink = replace(state, blink_until=now + self._ctx.timers.blink)
                tx.save_seat_state(blink, change=SeatChange.NONE)  # LED only, never public
            host_user = tx.user(session.user_id)
            assert host_user is not None
            tx.enqueue(
                [
                    notify.request_accepted(
                        request.seeker_id,
                        host_user.first_name,
                        facts.table_of(seat).label,
                        match.id,
                    )
                ],
                now,
            )
            others = [r.search_id for r in tx.pending_requests_for_session(session.id)]
        for search_id in others:  # the host is now in a match: other pending requests move on
            self._lifecycle.advance_search(search_id)
        return match.id

    def decline(self, user_id: str, request_id: str, mute: bool) -> RequestStatus:
        """Silent to the seeker (FR-36). `mute` also mutes the host (FR-28, D20)."""
        with self._ctx.repo.tx() as tx:
            request, session = _host_request(tx, user_id, request_id, Lock.WAIT)
            tx.update_request(replace(request, status=RequestStatus.DECLINED))
            if mute:
                tx.update_session(replace(session, muted=True))
            others = (
                [r.search_id for r in tx.pending_requests_for_session(session.id)] if mute else []
            )
        self._lifecycle.advance_search(request.search_id)
        for search_id in others:
            self._lifecycle.advance_search(search_id)
        return RequestStatus.DECLINED
