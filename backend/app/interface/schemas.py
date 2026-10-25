"""Request and response models: the executable form of REQUIREMENTS §7."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.types import (
    Group,
    HiddenReason,
    HostVisibility,
    Led,
    MatchStatus,
    PublicState,
    RecommendLevel,
    RequestStatus,
    SearchStatus,
)

SeatId = Field(min_length=1, max_length=64)


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class ErrorBody(Strict):
    error: str
    message: str


class Ok(Strict):
    ok: bool = True


# --- System -----------------------------------------------------------------


class Health(Strict):
    ok: bool
    db: bool


# --- Sensing ----------------------------------------------------------------


class ReadingIn(Strict):
    seat_id: str = SeatId
    object_present: bool
    human_present: bool


class ReadingsIn(Strict):
    node_id: str = Field(min_length=1, max_length=64)
    readings: list[ReadingIn] = Field(max_length=64)


class LedsOut(Strict):
    leds: dict[str, Led]


# --- Map --------------------------------------------------------------------


class BuildingSummary(Strict):
    id: str
    name: str
    is_simulated: bool
    open: int
    likely_opening: int
    occupied: int
    offline: int
    total: int


class SeatOut(Strict):
    id: str
    position: int
    state: PublicState


class TableOut(Strict):
    id: str
    label: str
    x: float
    y: float
    seats: list[SeatOut]


class FloorOut(Strict):
    floor: int
    tables: list[TableOut]


class BuildingDetail(Strict):
    id: str
    name: str
    is_simulated: bool
    floors: list[FloorOut]


class Recommendation(Strict):
    seat_id: str
    table_id: str
    floor: int
    kind: Literal[PublicState.OPEN, PublicState.LIKELY_OPENING]
    level: RecommendLevel


class BuildingFull(Strict):
    full: Literal[True] = True
    nearest_building_id: str | None


class HistoryPoint(Strict):
    hour: datetime
    open_avg: float


class SeatLookup(Strict):
    id: str
    building_id: str
    floor: int
    table_id: str
    table_label: str
    position: int
    state: PublicState


# --- Accounts ---------------------------------------------------------------


class DemoUser(Strict):
    id: str
    first_name: str
    major: str | None = None


class LoginIn(Strict):
    user_id: str = Field(min_length=1, max_length=64)


class HostStatusOut(Strict):
    session_id: str
    seat_id: str
    label: str | None
    muted: bool
    status: Literal[HostVisibility.FINDABLE, HostVisibility.HIDDEN]
    hidden_reason: HiddenReason | None


class MeOut(Strict):
    user: DemoUser | None
    host: HostStatusOut | None
    search_id: str | None
    match_id: str | None


# --- Search -----------------------------------------------------------------


class SearchIn(Strict):
    topic_raw: str = Field(min_length=1, max_length=200)
    group: Literal[Group.RELATED] | None = None


class GroupCount(Strict):
    building_id: str
    floor: int
    count: int


class SearchOut(Strict):
    search_id: str
    label: str
    course_code: str | None
    subject: str
    offered_group: Group
    has_real_hosts: bool
    same_course: list[GroupCount]
    related: list[GroupCount]


class Person(Strict):
    first_name: str
    major: str | None


class SearchStatusOut(Strict):
    status: SearchStatus
    seconds_left: int
    match_id: str | None = None
    asking: Person | None = None  # D43: the host holding the pending request
    request_id: str | None = None  # D53: that pending request
    joined: bool  # D53: False while the search is a preview
    label: str
    offered_group: Group


class SearchCancelOut(Strict):
    status: SearchStatus


# --- Host -------------------------------------------------------------------


class LinkIn(Strict):
    seat_id: str = SeatId


class LinkOut(Strict):
    session_id: str


class TopicIn(Strict):
    topic_raw: str = Field(min_length=1, max_length=200)
    about_me: str | None = Field(default=None, max_length=280)


class TopicOut(Strict):
    label: str
    course_code: str | None
    subject: str


class ToggleIn(Strict):
    open: bool


class ToggleOut(Strict):
    open: bool


class MuteIn(Strict):
    muted: bool


class MuteOut(Strict):
    muted: bool


class ConfirmOut(Strict):
    expires_at: datetime


class InboxItem(Strict):
    request_id: str
    seeker_first_name: str
    seeker_major: str | None
    course_label: str
    table_label: str
    seconds_left: int


# --- Requests and matches ---------------------------------------------------


class AcceptOut(Strict):
    match_id: str


class DeclineIn(Strict):
    mute: bool = False


class RequestStatusOut(Strict):
    status: RequestStatus


class MatchOut(Strict):
    status: MatchStatus
    role: Literal["host", "seeker"]
    other_first_name: str
    other_major: str | None
    building: str
    building_id: str
    floor: int
    table_id: str
    table_label: str
    assigned_seat_id: str | None
    alt_seat_id: str | None
    icebreaker: str
    card_url: str


class MatchStatusOut(Strict):
    status: MatchStatus


# --- Safety -----------------------------------------------------------------


class BlockIn(Strict):
    """Exactly one way to name the other person (D53): the request or match identifies them."""

    user_id: str | None = Field(None, min_length=1, max_length=64)
    request_id: str | None = Field(None, min_length=1, max_length=64)
    match_id: str | None = Field(None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _exactly_one(self) -> BlockIn:
        if sum(v is not None for v in (self.user_id, self.request_id, self.match_id)) != 1:
            raise ValueError("give exactly one of user_id, request_id or match_id")
        return self


class ReportIn(BlockIn):
    reason: str = Field(min_length=1, max_length=500)


# --- Push -------------------------------------------------------------------


class VapidKeyOut(Strict):
    key: str


class PushKeys(Strict):
    p256dh: str = Field(min_length=1, max_length=256)
    auth: str = Field(min_length=1, max_length=64)


class SubscribeIn(Strict):
    endpoint: str = Field(min_length=1, max_length=1024, pattern=r"^https://")
    keys: PushKeys


class UnsubscribeIn(Strict):
    endpoint: str = Field(min_length=1, max_length=1024)
