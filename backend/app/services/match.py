"""Matches (FR-38..42, D18, D25)."""

from __future__ import annotations

from dataclasses import replace

from app.domain import notifications as notify
from app.domain.geometry import nearest_seat
from app.domain.types import HostSession, Match, MatchStatus, PublicState, Seat, SeatChange
from app.services.context import Context
from app.services.errors import conflict, forbidden, not_found
from app.services.facts import Facts
from app.services.lifecycle import LifecycleService
from app.services.ports import Lock, Tx
from app.services.views import MatchView


def _participant(
    tx: Tx, user_id: str, match_id: str, lock: Lock = Lock.NONE
) -> tuple[Match, HostSession]:
    match = tx.match(match_id, lock)
    if match is None:
        raise not_found("match_not_found", "No such match")
    host = tx.session(match.host_session_id)
    assert host is not None
    if user_id not in (match.seeker_id, host.user_id):
        raise forbidden("not_in_match", "You're not part of this match")
    return match, host


def alternative_seat(facts: Facts, match: Match, host_seat: Seat) -> str | None:
    """FR-39 / D25: once the assigned seat is no longer open, both sides see the nearest open
    seat on its floor."""
    assigned = facts.seat(match.assigned_seat_id) if match.assigned_seat_id else None
    if assigned is None or facts.state(assigned) is PublicState.OPEN:
        return None
    candidates = [s for s in facts.open_seats_on_floor(assigned) if s.id != host_seat.id]
    found = nearest_seat(assigned, candidates)
    return found.id if found else None


class MatchService:
    def __init__(self, ctx: Context, lifecycle: LifecycleService) -> None:
        self._ctx = ctx
        self._lifecycle = lifecycle

    def view(self, user_id: str, match_id: str) -> MatchView:
        with self._ctx.repo.read() as tx:
            _participant(tx, user_id, match_id)
        self._lifecycle.advance_match(match_id)
        now = self._ctx.clock.now()
        with self._ctx.repo.read() as tx:
            match, host = _participant(tx, user_id, match_id)
            facts = Facts(tx, now, self._ctx.timers)
            host_seat = facts.seat(host.seat_id)
            assert host_seat is not None
            is_seeker = user_id == match.seeker_id
            other = tx.user(host.user_id if is_seeker else match.seeker_id)
            building = facts.building(host_seat.building_id)
            assert other is not None and building is not None
            return MatchView(
                status=match.status,
                role="seeker" if is_seeker else "host",
                other_first_name=other.first_name,
                other_major=other.major,
                building=building.name,
                building_id=building.id,
                floor=host_seat.floor,
                table_id=host_seat.table_id,
                table_label=facts.table_of(host_seat).label,
                assigned_seat_id=match.assigned_seat_id,
                alt_seat_id=alternative_seat(facts, match, host_seat),
                icebreaker=match.icebreaker,
                card_url=f"/cards/{match.card_key}.png",
            )

    def arrived(self, user_id: str, match_id: str) -> MatchStatus:
        """FR-40: only the seeker marks arrival; the host seat blinks again."""
        self._lifecycle.advance_match(match_id)
        now = self._ctx.clock.now()
        with self._ctx.repo.tx() as tx:
            match, host = _participant(tx, user_id, match_id, Lock.WAIT)
            if user_id != match.seeker_id:
                raise forbidden("not_in_match", "Only the person joining marks arrival")
            if match.status is not MatchStatus.ACTIVE:
                raise conflict("match_not_active", "This match has ended")
            tx.update_match(replace(match, status=MatchStatus.COMPLETED, arrived_at=now))
            state = tx.lock_seat_state(host.seat_id)
            if state is not None:
                blink = replace(state, blink_until=now + self._ctx.timers.blink)
                tx.save_seat_state(blink, change=SeatChange.NONE)  # LED only, never public
        return MatchStatus.COMPLETED

    def cancel(self, user_id: str, match_id: str) -> MatchStatus:
        """FR-41: either side cancels; the other side is told."""
        self._lifecycle.advance_match(match_id)
        now = self._ctx.clock.now()
        with self._ctx.repo.tx() as tx:
            match, host = _participant(tx, user_id, match_id, Lock.WAIT)
            if match.status is not MatchStatus.ACTIVE:
                return match.status
            tx.update_match(replace(match, status=MatchStatus.CANCELLED))
            other = host.user_id if user_id == match.seeker_id else match.seeker_id
            tx.enqueue([notify.match_cancelled(other, match.id)], now)
        return MatchStatus.CANCELLED
