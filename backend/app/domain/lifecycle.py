"""Transition decisions for host sessions, searches and matches (FR-25..42, NFR-2).

Each function looks at stored timestamps and returns what should happen. Services apply the
decision under a row lock; nothing here performs I/O or reads a clock.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.seat_engine import absent_for
from app.domain.types import (
    EndReason,
    HostSession,
    Match,
    MatchStatus,
    Search,
    SearchStatus,
    Seat,
    SeatState,
    StudyRequest,
    Timers,
)

# --- Host sessions (FR-26, FR-27, D18, D24) ---------------------------------


@dataclass(frozen=True)
class KeepSession:
    notify_confirm: bool = False


@dataclass(frozen=True)
class EndSession:
    reason: EndReason


def advance_host_session(
    s: HostSession, seat: Seat, seat_state: SeatState | None, now: datetime, t: Timers
) -> KeepSession | EndSession:
    if not s.live or seat.is_simulated:
        return KeepSession()
    if now >= s.expires_at + t.confirm_grace:
        return EndSession(EndReason.UNCONFIRMED)
    if seat_state is None or absent_for(seat_state, now) >= t.host_end:
        return EndSession(EndReason.NO_PERSON)
    pending = now >= s.expires_at
    already_told = s.confirm_notified_at is not None and s.confirm_notified_at >= s.expires_at
    return KeepSession(notify_confirm=pending and not already_told)


def confirm_due(s: HostSession, now: datetime, t: Timers) -> bool:
    return s.live and s.expires_at <= now < s.expires_at + t.confirm_grace


# --- Searches (FR-31..35, D15, D19, D22) ------------------------------------


class PendingStep(StrEnum):
    WAIT = "wait"
    EXPIRE = "expire"
    SKIP = "skip"


def pending_step(req: StudyRequest, host_can_receive: bool, now: datetime) -> PendingStep:
    if now >= req.expires_at:
        return PendingStep.EXPIRE
    if not host_can_receive:
        return PendingStep.SKIP
    return PendingStep.WAIT


def needs_send(search: Search, pending: StudyRequest | None) -> bool:
    return search.status is SearchStatus.ACTIVE and search.joined_at is not None and pending is None


@dataclass(frozen=True)
class SendTo:
    session_id: str


@dataclass(frozen=True)
class Exhaust:
    pass


def next_hop(
    search: Search, ranked_eligible: Sequence[str], requests_last_hour: int, t: Timers
) -> SendTo | Exhaust:
    """`ranked_eligible`: real, findable, unblocked hosts in the offered group, best first."""
    if len(search.tried_session_ids) >= t.max_hosts_per_search:
        return Exhaust()
    if requests_last_hour >= t.max_requests_per_hour:
        return Exhaust()
    for session_id in ranked_eligible:
        if session_id not in search.tried_session_ids:
            return SendTo(session_id)
    return Exhaust()


# --- Matches (FR-41, FR-42, D18) --------------------------------------------


class MatchStep(StrEnum):
    KEEP = "keep"
    CANCEL = "cancel"
    EXPIRE = "expire"


def advance_match(
    m: Match, host_seat_state: SeatState | None, now: datetime, t: Timers
) -> MatchStep:
    if m.status is not MatchStatus.ACTIVE:
        return MatchStep.KEEP
    if now >= m.expires_at:
        return MatchStep.EXPIRE
    if host_seat_state is None or absent_for(host_seat_state, now) >= t.host_leave_cancel:
        return MatchStep.CANCEL
    return MatchStep.KEEP
