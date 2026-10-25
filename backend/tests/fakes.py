"""Test doubles for the ports: controllable clock, recording notifier, in-memory repository.

`InMemoryRepository` is the reference implementation of the Repository port (D3). The shared
conformance suite in tests/repo_contract/ holds it and PostgresRepository to the same behavior,
including the uniqueness rules the database enforces with partial indexes.
"""

from __future__ import annotations

import copy
import threading
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.domain.types import (
    Building,
    HostSession,
    Match,
    MatchStatus,
    OutboxMessage,
    RequestStatus,
    Search,
    SearchStatus,
    Seat,
    SeatState,
    StoredReading,
    StudyRequest,
    Table,
    Topic,
    User,
)
from app.services.ports import Conflict, Lock, PushResult, PushSubscription

T0 = datetime(2026, 10, 24, 18, 0, 0, tzinfo=UTC)
HOUR = timedelta(hours=1)


class FakeClock:
    def __init__(self, start: datetime = T0) -> None:
        self._now = start
        self._mono = 1000.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
        self._mono += seconds


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, str]]] = []
        self.results: dict[str, PushResult] = {}

    def send(self, subscription: PushSubscription, payload: Mapping[str, str]) -> PushResult:
        result = self.results.get(subscription.endpoint, PushResult.SENT)
        if result is PushResult.SENT:
            self.sent.append((subscription.endpoint, dict(payload)))
        return result


@dataclass(frozen=True)
class Subscription:
    user_id: str
    endpoint: str
    p256dh: str
    auth: str


@dataclass
class OutboxEntry:
    id: int
    message: OutboxMessage
    created_at: datetime
    sent_at: datetime | None = None
    attempts: int = 0


@dataclass
class _Data:
    buildings: dict[str, Building] = field(default_factory=dict)
    tables: dict[str, Table] = field(default_factory=dict)
    seats: dict[str, Seat] = field(default_factory=dict)
    nodes: dict[str, datetime | None] = field(default_factory=dict)
    states: dict[str, SeatState] = field(default_factory=dict)
    readings: list[StoredReading] = field(default_factory=list)
    users: dict[str, User] = field(default_factory=dict)
    topics: dict[str, Topic] = field(default_factory=dict)
    sessions: dict[str, HostSession] = field(default_factory=dict)
    searches: dict[str, Search] = field(default_factory=dict)
    requests: dict[str, StudyRequest] = field(default_factory=dict)
    matches: dict[str, Match] = field(default_factory=dict)
    blocks: set[tuple[str, str]] = field(default_factory=set)
    reports: list[tuple[str, str, str, datetime]] = field(default_factory=list)
    subscriptions: dict[str, Subscription] = field(default_factory=dict)
    outbox: list[OutboxEntry] = field(default_factory=list)


class InMemoryTx:
    def __init__(self, d: _Data) -> None:
        self.d = d

    # Places
    def buildings(self) -> list[Building]:
        return list(self.d.buildings.values())

    def tables(self, building_id: str | None = None) -> list[Table]:
        return [t for t in self.d.tables.values() if building_id in (None, t.building_id)]

    def seats(self, building_id: str | None = None) -> list[Seat]:
        return [s for s in self.d.seats.values() if building_id in (None, s.building_id)]

    def seat(self, seat_id: str) -> Seat | None:
        return self.d.seats.get(seat_id)

    # Sensing
    def seat_states(self, seat_ids: Sequence[str]) -> dict[str, SeatState]:
        return {i: self.d.states[i] for i in seat_ids if i in self.d.states}

    def lock_seat_state(self, seat_id: str) -> SeatState | None:
        return self.d.states.get(seat_id)

    def save_seat_state(self, state: SeatState) -> None:
        self.d.states[state.seat_id] = state

    def touch_node(self, node_id: str, now: datetime) -> None:
        self.d.nodes[node_id] = now

    def insert_readings(self, rows: Sequence[StoredReading]) -> None:
        self.d.readings.extend(rows)

    def readings(self, seat_ids: Sequence[str], until: datetime) -> list[StoredReading]:
        wanted = set(seat_ids)
        rows = [r for r in self.d.readings if r.seat_id in wanted and r.time < until]
        return sorted(rows, key=lambda r: (r.seat_id, r.time))

    # Users
    def user(self, user_id: str) -> User | None:
        return self.d.users.get(user_id)

    def demo_users(self) -> list[User]:
        return sorted((u for u in self.d.users.values() if u.is_demo), key=lambda u: u.first_name)

    # Topic cache
    def cached_topic(self, key: str) -> Topic | None:
        return self.d.topics.get(key)

    def cache_topic(self, key: str, topic: Topic) -> None:
        self.d.topics.setdefault(key, topic)

    # Host sessions
    def insert_session(self, session: HostSession) -> None:
        for s in self.d.sessions.values():
            if s.live and (s.user_id == session.user_id or s.seat_id == session.seat_id):
                raise Conflict("one live session per user and per seat")
        self.d.sessions[session.id] = session

    def update_session(self, session: HostSession) -> None:
        self.d.sessions[session.id] = session

    def session(self, session_id: str, lock: Lock = Lock.NONE) -> HostSession | None:
        return self.d.sessions.get(session_id)

    def live_session_for_user(self, user_id: str, lock: Lock = Lock.NONE) -> HostSession | None:
        return next((s for s in self.d.sessions.values() if s.live and s.user_id == user_id), None)

    def live_sessions(self) -> list[HostSession]:
        return [s for s in self.d.sessions.values() if s.live]

    def live_sessions_for_seats(self, seat_ids: Sequence[str]) -> list[HostSession]:
        wanted = set(seat_ids)
        return [s for s in self.d.sessions.values() if s.live and s.seat_id in wanted]

    # Searches and requests
    def insert_search(self, search: Search) -> None:
        if search.status is SearchStatus.ACTIVE and self.active_search_for_user(search.seeker_id):
            raise Conflict("one active search per seeker")
        self.d.searches[search.id] = search

    def update_search(self, search: Search) -> None:
        self.d.searches[search.id] = search

    def search(self, search_id: str, lock: Lock = Lock.NONE) -> Search | None:
        return self.d.searches.get(search_id)

    def active_search_for_user(self, user_id: str) -> Search | None:
        return next(
            (
                s
                for s in self.d.searches.values()
                if s.seeker_id == user_id and s.status is SearchStatus.ACTIVE
            ),
            None,
        )

    def insert_request(self, request: StudyRequest) -> None:
        if request.status is RequestStatus.PENDING and self.pending_request_for_search(
            request.search_id
        ):
            raise Conflict("one pending request per search")
        self.d.requests[request.id] = request

    def update_request(self, request: StudyRequest) -> None:
        self.d.requests[request.id] = request

    def request(self, request_id: str, lock: Lock = Lock.NONE) -> StudyRequest | None:
        return self.d.requests.get(request_id)

    def pending_request_for_search(self, search_id: str) -> StudyRequest | None:
        return next(
            (
                r
                for r in self.d.requests.values()
                if r.search_id == search_id and r.status is RequestStatus.PENDING
            ),
            None,
        )

    def pending_requests_for_session(self, session_id: str) -> list[StudyRequest]:
        return sorted(
            (
                r
                for r in self.d.requests.values()
                if r.host_session_id == session_id and r.status is RequestStatus.PENDING
            ),
            key=lambda r: (r.created_at, r.id),
        )

    def count_requests_since(self, seeker_id: str, since: datetime) -> int:
        return sum(
            1
            for r in self.d.requests.values()
            if r.seeker_id == seeker_id and r.created_at >= since
        )

    # Matches
    def insert_match(self, match: Match) -> None:
        if match.status is MatchStatus.ACTIVE and (
            self.active_match_for_session(match.host_session_id)
            or self.active_match_for_seeker(match.seeker_id)
        ):
            raise Conflict("one active match per host session and per seeker")
        self.d.matches[match.id] = match

    def update_match(self, match: Match) -> None:
        self.d.matches[match.id] = match

    def match(self, match_id: str, lock: Lock = Lock.NONE) -> Match | None:
        return self.d.matches.get(match_id)

    def active_match_for_session(self, session_id: str) -> Match | None:
        return next(
            (
                m
                for m in self.d.matches.values()
                if m.host_session_id == session_id and m.status is MatchStatus.ACTIVE
            ),
            None,
        )

    def active_match_for_seeker(self, user_id: str) -> Match | None:
        return next(
            (
                m
                for m in self.d.matches.values()
                if m.seeker_id == user_id and m.status is MatchStatus.ACTIVE
            ),
            None,
        )

    def match_for_search(self, search_id: str) -> Match | None:
        accepted = {
            r.id
            for r in self.d.requests.values()
            if r.search_id == search_id and r.status is RequestStatus.ACCEPTED
        }
        return next((m for m in self.d.matches.values() if m.request_id in accepted), None)

    # Safety
    def insert_block(self, user_id: str, blocked_user_id: str) -> None:
        self.d.blocks.add((user_id, blocked_user_id))

    def blocked_with(self, user_id: str) -> set[str]:
        return {b for a, b in self.d.blocks if a == user_id} | {
            a for a, b in self.d.blocks if b == user_id
        }

    def insert_report(self, reporter_id: str, reported_id: str, reason: str, now: datetime) -> None:
        self.d.reports.append((reporter_id, reported_id, reason, now))

    # Push
    def upsert_subscription(
        self, user_id: str, endpoint: str, p256dh: str, auth: str, now: datetime
    ) -> None:
        self.d.subscriptions[endpoint] = Subscription(user_id, endpoint, p256dh, auth)

    def delete_subscription(self, endpoint: str, user_id: str | None = None) -> None:
        sub = self.d.subscriptions.get(endpoint)
        if sub is not None and user_id in (None, sub.user_id):
            del self.d.subscriptions[endpoint]

    def subscriptions_for(self, user_id: str) -> list[PushSubscription]:
        return [s for s in self.d.subscriptions.values() if s.user_id == user_id]

    def enqueue(self, messages: Sequence[OutboxMessage], now: datetime) -> None:
        for m in messages:
            self.d.outbox.append(OutboxEntry(len(self.d.outbox) + 1, m, now))

    def claim_outbox(self, limit: int) -> list[OutboxEntry]:
        return [e for e in self.d.outbox if e.sent_at is None][:limit]

    def mark_outbox(self, row_id: int, sent_at: datetime | None, attempts: int) -> None:
        entry = self.d.outbox[row_id - 1]
        entry.sent_at, entry.attempts = sent_at, attempts

    # Scheduler
    def _absent_before(self, seat_id: str, before: datetime) -> bool:
        st = self.d.states.get(seat_id)
        return st is None or st.last_human is None or st.last_human < before

    def due_search_ids(self, now: datetime, human_fresh_before: datetime) -> list[str]:
        out = []
        for r in self.d.requests.values():
            if r.status is not RequestStatus.PENDING:
                continue
            host = self.d.sessions[r.host_session_id]
            if (
                r.expires_at <= now
                or not host.live
                or self._absent_before(host.seat_id, human_fresh_before)
            ):
                out.append(r.search_id)
        return sorted(set(out))

    def due_match_ids(self, now: datetime, host_absent_before: datetime) -> list[str]:
        out = []
        for m in self.d.matches.values():
            if m.status is not MatchStatus.ACTIVE:
                continue
            host = self.d.sessions[m.host_session_id]
            if m.expires_at <= now or self._absent_before(host.seat_id, host_absent_before):
                out.append(m.id)
        return sorted(out)

    def due_session_ids(self, now: datetime, host_absent_before: datetime) -> list[str]:
        out = []
        for s in self.d.sessions.values():
            if not s.live or self.d.seats[s.seat_id].is_simulated:
                continue
            if s.expires_at <= now or self._absent_before(s.seat_id, host_absent_before):
                out.append(s.id)
        return sorted(out)

    def demo_request_ids(self, created_before: datetime) -> list[str]:
        pending = [
            r
            for r in self.d.requests.values()
            if r.status is RequestStatus.PENDING
            and r.created_at <= created_before
            and self.d.seats[self.d.sessions[r.host_session_id].seat_id].is_simulated
        ]
        return [r.id for r in sorted(pending, key=lambda r: (r.created_at, r.id))]


class InMemoryRepository:
    def __init__(self) -> None:
        self.data = _Data()
        self._lock = threading.RLock()  # one transaction at a time: every row is "locked"

    @contextmanager
    def tx(self) -> Iterator[InMemoryTx]:
        with self._lock:
            snapshot = copy.deepcopy(self.data)
            try:
                yield InMemoryTx(self.data)
            except BaseException:
                self.data.__dict__.update(snapshot.__dict__)
                raise

    @contextmanager
    def read(self) -> Iterator[InMemoryTx]:
        with self._lock:
            yield InMemoryTx(self.data)

    def ping(self) -> bool:
        return True

    def history(
        self, building_id: str, since: datetime, until: datetime, offline: timedelta
    ) -> list[tuple[datetime, float]]:
        """Reference implementation of FR-49 / D31 (see ARCHITECTURE §10)."""
        with self.read() as tx:
            seats = tx.seats(building_id)
            intervals: list[tuple[datetime, datetime]] = []  # time spent open, per seat
            for seat in seats:
                rows = tx.readings([seat.id], until)
                state = self.data.states.get(seat.id)
                cap = until
                if state is not None and state.last_seen is not None:
                    cap = min(until, state.last_seen + offline)  # silent node: state unknown
                for i, row in enumerate(rows):
                    stop = rows[i + 1].time if i + 1 < len(rows) else until
                    start, stop = max(row.time, since), min(stop, cap)
                    is_open = row.online and not row.object_present and not row.human_present
                    if is_open and stop > start:
                        intervals.append((start, stop))
        out = []
        hour = since
        while hour < until:
            end = min(hour + HOUR, until)
            secs = sum(
                (min(stop, end) - max(start, hour)).total_seconds()
                for start, stop in intervals
                if start < end and stop > hour
            )
            out.append((hour, secs / (end - hour).total_seconds()))
            hour += HOUR
        return out
