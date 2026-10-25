"""Small builders for domain records, so tests state only what matters to them."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from app.domain.types import (
    Building,
    Group,
    HostSession,
    InternalState,
    Match,
    MatchStatus,
    RequestStatus,
    Search,
    SearchStatus,
    Seat,
    SeatState,
    StudyRequest,
    Table,
)
from tests.fakes import T0


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def building(bid: str = "b", lat: float | None = 30.0, lng: float | None = -97.0) -> Building:
    return Building(bid, bid.upper(), False, 50, lat, lng)


def table(tid: str = "t1", bid: str = "b", floor: int = 1, x: float = 0, y: float = 0) -> Table:
    return Table(tid, bid, floor, tid, x, y)


def seat(
    sid: str,
    tbl: Table | None = None,
    position: int = 1,
    simulated: bool = False,
) -> Seat:
    tbl = tbl or table()
    return Seat(
        sid,
        tbl.id,
        tbl.building_id,
        tbl.floor,
        position,
        tbl.x,
        tbl.y,
        simulated,
        None if simulated else "n1",
    )


def present(sid: str, last_human_s: float, now_s: float = 0) -> SeatState:
    """A seat whose occupant was last seen at `last_human_s`; readings continue until now."""
    return replace(
        SeatState.never_seen(sid),
        state=InternalState.OCCUPIED,
        candidate_state=InternalState.OCCUPIED,
        last_human=at(last_human_s),
        last_object=at(max(last_human_s, now_s)),
        last_seen=at(max(last_human_s, now_s)),
    )


def session(
    sid: str = "h1",
    user: str = "u-host",
    seat_id: str = "s1",
    *,
    topic: bool = True,
    course: str | None = "CH 320M",
    subject: str = "chemistry",
    started_s: float = 0,
    expires_s: float = 10800,
    muted: bool = False,
    ended: bool = False,
) -> HostSession:
    return HostSession(
        id=sid,
        user_id=user,
        seat_id=seat_id,
        topic_raw="orgo" if topic else None,
        course_code=course if topic else None,
        subject=subject if topic else None,
        keywords=("orgo",) if topic else (),
        about_me=None,
        open=True,
        muted=muted,
        started_at=at(started_s),
        expires_at=at(expires_s),
        ended_at=at(1) if ended else None,
        end_reason=None,
        confirm_notified_at=None,
    )


def search(
    *, joined: bool = True, tried: tuple[str, ...] = (), status: SearchStatus = SearchStatus.ACTIVE
) -> Search:
    return Search(
        id="q1",
        seeker_id="u-seek",
        topic_raw="orgo",
        course_code="CH 320M",
        subject="chemistry",
        keywords=("orgo",),
        label="CH 320M",
        offered_group=Group.SAME_COURSE,
        status=status,
        tried_session_ids=tried,
        created_at=at(0),
        joined_at=at(0) if joined else None,
    )


def request(expires_s: float = 120) -> StudyRequest:
    return StudyRequest("r1", "q1", "u-seek", "h1", RequestStatus.PENDING, at(0), at(expires_s))


def match(expires_s: float = 1200, status: MatchStatus = MatchStatus.ACTIVE) -> Match:
    return Match(
        "m1", "r1", "u-seek", "h1", "hi", "chemistry", "s2", status, at(0), at(expires_s), None
    )
