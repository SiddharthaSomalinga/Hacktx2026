"""Ports: what services need from the outside world. Adapters implement these."""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Final, Protocol

from app.domain.types import (
    Building,
    HostSession,
    Match,
    OutboxMessage,
    Search,
    Seat,
    SeatChange,
    SeatState,
    StoredReading,
    StudyRequest,
    Table,
    Topic,
    User,
    UserChange,
)


class Conflict(Exception):
    """A uniqueness rule in the store rejected the write (e.g. one active search per seeker)."""


class Unavailable(Exception):
    """The store cannot be reached right now (connection refused, pool exhausted, lost link)."""


class Lock(StrEnum):
    """How a read locks its row. `SKIP` returns None instead of waiting on a locked row."""

    NONE = "none"
    WAIT = "wait"
    SKIP = "skip"


class Clock(Protocol):
    def now(self) -> datetime: ...

    def monotonic(self) -> float: ...


class HostTopic(Protocol):
    @property
    def id(self) -> str: ...

    @property
    def topic(self) -> Topic: ...

    @property
    def about_me(self) -> str | None: ...


class TopicAI(Protocol):
    def normalize_topic(self, text: str) -> Topic: ...

    def rank_hosts(self, seeker: Topic, hosts: Sequence[HostTopic]) -> dict[str, int]: ...

    def icebreaker(self, a: Topic, b: Topic) -> str: ...


class PushResult(StrEnum):
    SENT = "sent"
    GONE = "gone"
    FAILED = "failed"


class PushSubscription(Protocol):
    @property
    def endpoint(self) -> str: ...

    @property
    def p256dh(self) -> str: ...

    @property
    def auth(self) -> str: ...


class Notifier(Protocol):
    def send(self, subscription: PushSubscription, payload: Mapping[str, str]) -> PushResult: ...


class PushOutcome(StrEnum):
    """What became of one outbox row in a drain."""

    SENT = "sent"  # every subscription took it, or none were left
    RETRY = "retry"  # a send failed; the row stays unsent for a later tick
    GAVE_UP = "gave_up"  # failed PUSH_MAX_ATTEMPTS times


class Metrics(Protocol):
    """What GET /metrics reports (D60). Called from request threads and the worker thread."""

    def observe_request(self, method: str, route: str, status: int, seconds: float) -> None: ...
    def observe_tick(self, seconds: float, due: int) -> None: ...
    def count_push(self, outcome: PushOutcome) -> None: ...
    def count_ai_fallback(self, call: str) -> None: ...
    def stream_opened(self) -> None: ...
    def stream_closed(self, seconds: float) -> None: ...
    def count_bytes(self, route: str, n: int) -> None: ...
    def render(self, outbox_unsent: int) -> tuple[bytes, str]:
        """The exposition and its media type."""
        ...


class NullMetrics:
    """Records nothing: the default for contexts built without metrics (tests, scripts)."""

    def observe_request(self, method: str, route: str, status: int, seconds: float) -> None:
        pass

    def observe_tick(self, seconds: float, due: int) -> None:
        pass

    def count_push(self, outcome: PushOutcome) -> None:
        pass

    def count_ai_fallback(self, call: str) -> None:
        pass

    def stream_opened(self) -> None:
        pass

    def stream_closed(self, seconds: float) -> None:
        pass

    def count_bytes(self, route: str, n: int) -> None:
        pass

    def render(self, outbox_unsent: int) -> tuple[bytes, str]:
        return b"", "text/plain; charset=utf-8"


@dataclass(frozen=True)
class MapHint:
    """A building's public seat states changed (D61)."""

    building_id: str


@dataclass(frozen=True)
class UserHint:
    """Something a user's own GETs return may have changed (D61)."""

    user_id: str
    changes: frozenset[UserChange]


@dataclass(frozen=True)
class Resync:
    """The hint feed (re)connected: hints may have been missed, so treat everything as dirty."""


@dataclass(frozen=True)
class Lost:
    """The hint feed lost its connection; until the next `Resync`, hints are not arriving."""


Hint = MapHint | UserHint | Resync | Lost


class OutboxRow(Protocol):
    @property
    def id(self) -> int: ...

    @property
    def message(self) -> OutboxMessage: ...

    @property
    def attempts(self) -> int: ...


class Tx(Protocol):
    """One unit of work. Leaving the `with` block commits; an exception rolls back."""

    # Places
    def buildings(self) -> list[Building]: ...
    def tables(self, building_id: str | None = None) -> list[Table]: ...
    def seats(self, building_id: str | None = None) -> list[Seat]: ...
    def seat(self, seat_id: str) -> Seat | None: ...

    # Sensing
    def seat_states(self, seat_ids: Sequence[str]) -> dict[str, SeatState]: ...
    def lock_seat_state(self, seat_id: str) -> SeatState | None: ...
    def save_seat_state(self, state: SeatState, *, change: SeatChange) -> None:
        """`change` (from `seat_change`) is required, so no writer can forget the live hint."""
        ...

    def touch_node(self, node_id: str, now: datetime) -> None: ...
    def insert_readings(self, rows: Sequence[StoredReading]) -> None: ...
    def readings(self, seat_ids: Sequence[str], until: datetime) -> list[StoredReading]: ...

    # Users
    def user(self, user_id: str) -> User | None: ...
    def demo_users(self) -> list[User]: ...

    # Topic cache
    def cached_topic(self, key: str) -> Topic | None: ...
    def cache_topic(self, key: str, topic: Topic) -> None: ...

    # Host sessions
    def insert_session(self, session: HostSession) -> None: ...
    def update_session(self, session: HostSession) -> None: ...
    def session(self, session_id: str, lock: Lock = Lock.NONE) -> HostSession | None: ...
    def live_session_for_user(self, user_id: str, lock: Lock = Lock.NONE) -> HostSession | None: ...
    def live_sessions(self) -> list[HostSession]: ...
    def live_sessions_for_seats(self, seat_ids: Sequence[str]) -> list[HostSession]: ...

    # Searches and requests
    def insert_search(self, search: Search) -> None: ...
    def update_search(self, search: Search) -> None: ...
    def search(self, search_id: str, lock: Lock = Lock.NONE) -> Search | None: ...
    def active_search_for_user(self, user_id: str) -> Search | None: ...
    def insert_request(self, request: StudyRequest) -> None: ...
    def update_request(self, request: StudyRequest) -> None: ...
    def request(self, request_id: str, lock: Lock = Lock.NONE) -> StudyRequest | None: ...
    def pending_request_for_search(self, search_id: str) -> StudyRequest | None: ...
    def pending_requests_for_session(self, session_id: str) -> list[StudyRequest]: ...
    def count_requests_since(self, seeker_id: str, since: datetime) -> int: ...

    # Matches
    def insert_match(self, match: Match) -> None: ...
    def update_match(self, match: Match) -> None: ...
    def match(self, match_id: str, lock: Lock = Lock.NONE) -> Match | None: ...
    def active_match_for_session(self, session_id: str) -> Match | None: ...
    def active_match_for_seeker(self, user_id: str) -> Match | None: ...
    def match_for_search(self, search_id: str) -> Match | None: ...

    # Safety
    def insert_block(self, user_id: str, blocked_user_id: str) -> None: ...
    def blocked_with(self, user_id: str) -> set[str]: ...
    def insert_report(
        self, reporter_id: str, reported_id: str, reason: str, now: datetime
    ) -> None: ...

    # Push
    def upsert_subscription(
        self, user_id: str, endpoint: str, p256dh: str, auth: str, now: datetime
    ) -> None: ...
    def delete_subscription(self, endpoint: str, user_id: str | None = None) -> None: ...
    def subscriptions_for(self, user_id: str) -> list[PushSubscription]: ...
    def enqueue(self, messages: Sequence[OutboxMessage], now: datetime) -> None: ...
    def claim_outbox(self, limit: int) -> Sequence[OutboxRow]: ...
    def mark_outbox(self, row_id: int, sent_at: datetime | None, attempts: int) -> None: ...
    def outbox_unsent(self) -> int: ...

    # Scheduler: ids of rows whose time-only deadline has passed
    def due_search_ids(self, now: datetime, human_fresh_before: datetime) -> list[str]: ...
    def idle_search_ids(self) -> list[str]:
        """Active, joined searches with no pending request: each should be mid-send."""
        ...

    def due_match_ids(self, now: datetime, host_absent_before: datetime) -> list[str]: ...
    def due_session_ids(self, now: datetime, host_absent_before: datetime) -> list[str]: ...
    def demo_request_ids(self, created_before: datetime) -> list[str]: ...

    # Live hints (D61): sent on commit, dropped on rollback
    def touch_users(self, user_ids: Sequence[str], change: UserChange) -> None:
        """Hint users whose views changed with no row written for them (the sweep)."""
        ...


# Every Tx method that writes, with the user changes its hints carry (D61). A seat-state write
# is classified by its `change` argument instead. A new writer must be listed here, or the
# repository contract fails; one with no effect on any user's view gets an empty set.
WRITE_EFFECTS: Final[Mapping[str, frozenset[UserChange]]] = {
    "save_seat_state": frozenset({UserChange.SEAT}),
    "touch_node": frozenset(),
    "insert_readings": frozenset(),
    "cache_topic": frozenset(),
    "insert_session": frozenset({UserChange.SESSION}),
    "update_session": frozenset({UserChange.SESSION}),
    "insert_search": frozenset({UserChange.SEARCH}),
    "update_search": frozenset({UserChange.SEARCH}),
    "insert_request": frozenset({UserChange.REQUEST}),
    "update_request": frozenset({UserChange.REQUEST}),
    "insert_match": frozenset({UserChange.MATCH}),
    "update_match": frozenset({UserChange.MATCH}),
    "insert_block": frozenset({UserChange.BLOCK}),
    "insert_report": frozenset(),
    "upsert_subscription": frozenset(),
    "delete_subscription": frozenset(),
    "enqueue": frozenset(),
    "claim_outbox": frozenset(),
    "mark_outbox": frozenset(),
    "touch_users": frozenset(UserChange),
}

# The rest of Tx only reads. Listed so that the contract test can tell a new method apart.
READS: Final[frozenset[str]] = frozenset(
    {
        "buildings", "tables", "seats", "seat", "seat_states", "lock_seat_state", "readings",
        "user", "demo_users", "cached_topic", "session", "live_session_for_user",
        "live_sessions", "live_sessions_for_seats", "search", "active_search_for_user",
        "request", "pending_request_for_search", "pending_requests_for_session",
        "count_requests_since", "match", "active_match_for_session", "active_match_for_seeker",
        "match_for_search", "blocked_with", "subscriptions_for", "outbox_unsent",
        "due_search_ids", "idle_search_ids", "due_match_ids", "due_session_ids",
        "demo_request_ids",
    }
)  # fmt: skip


class Repository(Protocol):
    def tx(self) -> AbstractContextManager[Tx]:
        """Read-write unit of work on the primary."""
        ...

    def read(self) -> AbstractContextManager[Tx]:
        """Read-only unit of work; may use a replica (D32). Never lock or write here."""
        ...

    def ping(self) -> bool: ...

    def hints(self) -> AsyncIterator[Hint]:
        """Hints from every committed write, on every instance (D61). Starts with `Resync`;
        yields `Lost` when the connection fails and `Resync` again once it is back, because
        hints may be lost meanwhile. Never ends on its own; cancel the consumer to stop it."""
        ...

    def history(
        self, building_id: str, since: datetime, until: datetime, offline: timedelta
    ) -> list[tuple[datetime, float]]:
        """Hourly average open seats over [since, until) from a building's change-only readings
        (FR-49). A real seat's last state ends at `last_seen + offline` (state unknown after)."""
        ...
