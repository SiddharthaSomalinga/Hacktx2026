"""Core vocabulary: enums and immutable records shared by every layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum


class InternalState(StrEnum):
    """Committed seat state. `away` never leaves the backend (FR-6)."""

    OPEN = "open"
    OCCUPIED = "occupied"
    AWAY = "away"


class PublicState(StrEnum):
    OPEN = "open"
    OCCUPIED = "occupied"
    LIKELY_OPENING = "likely_opening"
    OFFLINE = "offline"


class Led(StrEnum):
    GREEN = "green"
    RED = "red"
    YELLOW = "yellow"
    BLUE_BLINK = "blue_blink"
    OFF = "off"


class SearchStatus(StrEnum):
    ACTIVE = "active"
    MATCHED = "matched"
    EXHAUSTED = "exhausted"
    CANCELLED = "cancelled"


class RequestStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class MatchStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class EndReason(StrEnum):
    TOGGLED_OFF = "toggled_off"
    NO_PERSON = "no_person"
    UNCONFIRMED = "unconfirmed"


class Group(StrEnum):
    SAME_COURSE = "same_course"
    RELATED = "related"


class RecommendLevel(StrEnum):
    TABLE = "table"
    FLOOR = "floor"
    BUILDING = "building"


class HostVisibility(StrEnum):
    FINDABLE = "findable"
    HIDDEN = "hidden"
    ENDED = "ended"


class HiddenReason(StrEnum):
    NEEDS_TOPIC = "needs_topic"
    CONFIRM_PENDING = "confirm_pending"
    IN_MATCH = "in_match"
    AWAY = "away"
    MUTED = "muted"
    TABLE_FULL = "table_full"


class OutboxKind(StrEnum):
    REQUEST_RECEIVED = "request_received"
    REQUEST_ACCEPTED = "request_accepted"
    MATCH_CANCELLED = "match_cancelled"
    MATCH_EXPIRED = "match_expired"
    SEARCH_EXHAUSTED = "search_exhausted"
    CONFIRM_NEEDED = "confirm_needed"
    SESSION_ENDED = "session_ended"


@dataclass(frozen=True)
class Timers:
    """Every threshold the domain needs (NFR-6). Built from config by the caller."""

    ghost: timedelta
    debounce: timedelta
    offline: timedelta
    human_fresh: timedelta
    request_timeout: timedelta
    host_end: timedelta
    host_leave_cancel: timedelta
    match_timeout: timedelta
    blink: timedelta
    session_max: timedelta
    confirm_grace: timedelta
    sim_slot: timedelta
    max_hosts_per_search: int
    max_requests_per_hour: int


# --- Places -----------------------------------------------------------------


@dataclass(frozen=True)
class Building:
    id: str
    name: str
    is_simulated: bool
    busyness: int
    lat: float | None
    lng: float | None


@dataclass(frozen=True)
class Table:
    id: str
    building_id: str
    floor: int
    label: str
    x: float
    y: float


@dataclass(frozen=True)
class Seat:
    """A seat with its table's placement denormalized in, so pure code never joins."""

    id: str
    table_id: str
    building_id: str
    floor: int
    position: int
    x: float
    y: float
    is_simulated: bool
    node_id: str | None


@dataclass(frozen=True)
class SeatView:
    seat: Seat
    state: PublicState


# --- Sensing ----------------------------------------------------------------


@dataclass(frozen=True)
class Reading:
    seat_id: str
    object_present: bool
    human_present: bool


@dataclass(frozen=True)
class StoredReading:
    """One `seat_readings` row. `online=False` rows mark an offline gap (D31)."""

    seat_id: str
    time: datetime
    online: bool
    object_present: bool | None
    human_present: bool | None


@dataclass(frozen=True)
class SeatState:
    seat_id: str
    state: InternalState
    candidate_state: InternalState
    candidate_since: datetime | None
    state_since: datetime | None
    away_since: datetime | None
    last_object: datetime | None
    last_human: datetime | None
    last_seen: datetime | None
    blink_until: datetime | None

    @staticmethod
    def never_seen(seat_id: str) -> SeatState:
        return SeatState(
            seat_id=seat_id,
            state=InternalState.OPEN,
            candidate_state=InternalState.OPEN,
            candidate_since=None,
            state_since=None,
            away_since=None,
            last_object=None,
            last_human=None,
            last_seen=None,
            blink_until=None,
        )


# --- People and topics ------------------------------------------------------


@dataclass(frozen=True)
class User:
    id: str
    first_name: str
    is_demo: bool


@dataclass(frozen=True)
class Topic:
    course_code: str | None
    subject: str
    keywords: tuple[str, ...]
    label: str


@dataclass(frozen=True)
class HostSession:
    id: str
    user_id: str
    seat_id: str
    topic_raw: str | None
    course_code: str | None
    subject: str | None
    keywords: tuple[str, ...]
    about_me: str | None
    open: bool
    muted: bool
    started_at: datetime
    expires_at: datetime
    ended_at: datetime | None
    end_reason: EndReason | None
    confirm_notified_at: datetime | None
    label: str | None = None

    @property
    def has_topic(self) -> bool:
        return self.subject is not None

    @property
    def live(self) -> bool:
        return self.ended_at is None


@dataclass(frozen=True)
class Search:
    id: str
    seeker_id: str
    topic_raw: str
    course_code: str | None
    subject: str
    keywords: tuple[str, ...]
    label: str
    offered_group: Group
    status: SearchStatus
    tried_session_ids: tuple[str, ...]
    created_at: datetime
    joined_at: datetime | None


@dataclass(frozen=True)
class StudyRequest:
    id: str
    search_id: str
    seeker_id: str
    host_session_id: str
    status: RequestStatus
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class Match:
    id: str
    request_id: str
    seeker_id: str
    host_session_id: str
    icebreaker: str
    card_key: str
    assigned_seat_id: str | None
    status: MatchStatus
    created_at: datetime
    expires_at: datetime
    arrived_at: datetime | None


@dataclass(frozen=True)
class OutboxMessage:
    user_id: str
    kind: OutboxKind
    payload: dict[str, str] = field(default_factory=dict)
