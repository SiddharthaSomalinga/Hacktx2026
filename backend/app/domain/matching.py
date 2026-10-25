"""Who is findable, how searches group hosts, and how they are ranked (FR-24, 29, 30, 48)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime

from app.domain.catalog import GENERAL_SUBJECT
from app.domain.seat_engine import human_present_now
from app.domain.types import (
    Group,
    HiddenReason,
    HostSession,
    HostVisibility,
    Seat,
    SeatState,
    Timers,
)


@dataclass(frozen=True)
class HostFacts:
    """Everything FR-24 looks at, gathered by the service."""

    session: HostSession
    seat: Seat
    seat_state: SeatState | None
    has_active_match: bool
    table_open_seats: int


def host_status(
    f: HostFacts, now: datetime, t: Timers
) -> tuple[HostVisibility, HiddenReason | None]:
    """FR-24 / FR-48. The first failing condition is the reason the host UI shows."""
    s = f.session
    if not s.live:
        return HostVisibility.ENDED, None
    if not s.has_topic:
        return HostVisibility.HIDDEN, HiddenReason.NEEDS_TOPIC
    if f.seat.is_simulated:
        return HostVisibility.FINDABLE, None  # seeded simulated hosts are always findable
    if now >= s.expires_at:
        return HostVisibility.HIDDEN, HiddenReason.CONFIRM_PENDING
    if f.has_active_match:
        return HostVisibility.HIDDEN, HiddenReason.IN_MATCH
    if f.seat_state is None or not human_present_now(f.seat_state, now, t):
        return HostVisibility.HIDDEN, HiddenReason.AWAY
    if s.muted:
        return HostVisibility.HIDDEN, HiddenReason.MUTED
    if f.table_open_seats < 1:
        return HostVisibility.HIDDEN, HiddenReason.TABLE_FULL
    return HostVisibility.FINDABLE, None


def can_still_receive(visibility: HostVisibility, reason: HiddenReason | None) -> bool:
    """Whether a host's *pending* request stays pending. Absence, muting, an ended session,
    a pending confirmation or another match skip it (FR-25). A full table does not: the host
    can still accept, and the seeker gets the nearest open seat on the floor (Q13)."""
    return visibility is HostVisibility.FINDABLE or reason is HiddenReason.TABLE_FULL


def group_of(
    seeker_course: str | None,
    seeker_subject: str,
    host_course: str | None,
    host_subject: str | None,
) -> Group | None:
    """Same course needs equal, known course codes. Related needs an equal real subject
    ("general" is not a subject, so it never groups strangers together)."""
    if seeker_course is not None and seeker_course == host_course:
        return Group.SAME_COURSE
    if (
        host_subject is not None
        and seeker_subject == host_subject
        and seeker_subject != GENERAL_SUBJECT
    ):
        return Group.RELATED
    return None


def offered_group(same_course_hosts: int, pinned: Group | None) -> Group:
    """D19: same course if that group has any host, otherwise related, unless pinned (FR-54)."""
    if pinned is not None:
        return pinned
    return Group.SAME_COURSE if same_course_hosts > 0 else Group.RELATED


def aggregate(places: Iterable[tuple[str, int]]) -> list[tuple[str, int, int]]:
    """(building_id, floor) per host → [(building_id, floor, count)], busiest first."""
    counts = Counter(places)
    return sorted(((b, f, n) for (b, f), n in counts.items()), key=lambda r: (-r[2], r[0], r[1]))


def rank(sessions: Iterable[HostSession], scores: Mapping[str, int]) -> list[HostSession]:
    """Highest score first; ties go to the host who has been waiting longest, then id."""
    return sorted(sessions, key=lambda s: (-scores.get(s.id, 0), s.started_at, s.id))
