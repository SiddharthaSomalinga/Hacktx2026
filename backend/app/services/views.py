"""What services hand back to the interface. Field names match the API schemas."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.types import (
    Group,
    HiddenReason,
    HostVisibility,
    MatchStatus,
    PublicState,
    RecommendLevel,
    SearchStatus,
    User,
)


@dataclass(frozen=True)
class Cached:
    """Serialized JSON and the strong ETag computed from exactly those bytes (D32)."""

    content: bytes
    etag: str


@dataclass(frozen=True)
class RecommendationView:
    seat_id: str
    table_id: str
    floor: int
    kind: PublicState
    level: RecommendLevel


@dataclass(frozen=True)
class BuildingFullView:
    nearest_building_id: str | None
    full: bool = True


@dataclass(frozen=True)
class HostStatusView:
    session_id: str
    seat_id: str
    label: str | None
    muted: bool
    status: HostVisibility
    hidden_reason: HiddenReason | None


@dataclass(frozen=True)
class MeView:
    user: User | None
    host: HostStatusView | None
    search_id: str | None
    match_id: str | None


@dataclass(frozen=True)
class GroupCountView:
    building_id: str
    floor: int
    count: int


@dataclass(frozen=True)
class SearchView:
    search_id: str
    label: str
    course_code: str | None
    subject: str
    offered_group: Group
    has_real_hosts: bool
    same_course: list[GroupCountView]
    related: list[GroupCountView]


@dataclass(frozen=True)
class SearchStatusView:
    status: SearchStatus
    seconds_left: int
    match_id: str | None


@dataclass(frozen=True)
class InboxItemView:
    request_id: str
    course_label: str
    table_label: str
    seconds_left: int


@dataclass(frozen=True)
class MatchView:
    status: MatchStatus
    role: str
    other_first_name: str
    building: str
    floor: int
    table_label: str
    assigned_seat_id: str | None
    alt_seat_id: str | None
    icebreaker: str
    card_url: str


@dataclass(frozen=True)
class ConfirmView:
    expires_at: datetime
