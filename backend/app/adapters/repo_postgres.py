"""PostgresRepository: every SQL statement in the backend lives here (ARCH §3).

All statements are parameterized. Row locks use FOR UPDATE, or FOR UPDATE SKIP LOCKED for the
scheduler and outbox (D29, D30). Partial unique indexes back the one-of rules; a violation is
raised as the port's `Conflict` so services translate it the same way for every repository.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import psycopg
from psycopg import Connection
from psycopg.rows import TupleRow, dict_row
from psycopg_pool import ConnectionPool

from app.adapters.db import BoundedConnection, make_pool
from app.adapters.history_sql import HISTORY_SQL
from app.domain.types import (
    Building,
    EndReason,
    Group,
    HostSession,
    InternalState,
    Match,
    MatchStatus,
    OutboxKind,
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
from app.services.ports import Conflict, Lock, PushSubscription, Unavailable

log = logging.getLogger("ghostseats.repo")

Row = dict[str, Any]

_LOCK_SQL = {
    Lock.NONE: "",
    Lock.WAIT: " FOR UPDATE",
    Lock.SKIP: " FOR UPDATE SKIP LOCKED",
}


def _uuid(value: str) -> uuid.UUID | None:
    """Ids arrive from URLs; a malformed one is simply 'not found', never a database error."""
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        return None


def _str(value: Any) -> str | None:
    return None if value is None else str(value)


@dataclass(frozen=True)
class _Subscription:
    endpoint: str
    p256dh: str
    auth: str


@dataclass(frozen=True)
class _OutboxRow:
    id: int
    message: OutboxMessage
    attempts: int


# --- row mappers -----------------------------------------------------------------

_SEAT_COLS = """s.id, s.table_id, t.building_id, t.floor, s.position, t.x, t.y, s.is_simulated,
                s.node_id"""


def _seat(r: Row) -> Seat:
    return Seat(
        r["id"], r["table_id"], r["building_id"], r["floor"], r["position"],
        float(r["x"]), float(r["y"]), r["is_simulated"], r["node_id"],
    )  # fmt: skip


def _seat_state(r: Row) -> SeatState:
    return SeatState(
        seat_id=r["seat_id"],
        state=InternalState(r["state"]),
        candidate_state=InternalState(r["candidate_state"]),
        candidate_since=r["candidate_since"],
        state_since=r["state_since"],
        away_since=r["away_since"],
        last_object=r["last_object"],
        last_human=r["last_human"],
        last_seen=r["last_seen"],
        blink_until=r["blink_until"],
    )


def _session(r: Row) -> HostSession:
    return HostSession(
        id=str(r["id"]),
        user_id=r["user_id"],
        seat_id=r["seat_id"],
        topic_raw=r["topic_raw"],
        course_code=r["course_code"],
        subject=r["subject"],
        keywords=tuple(r["keywords"] or ()),
        about_me=r["about_me"],
        open=r["open"],
        muted=r["muted"],
        started_at=r["started_at"],
        expires_at=r["expires_at"],
        ended_at=r["ended_at"],
        end_reason=EndReason(r["end_reason"]) if r["end_reason"] else None,
        confirm_notified_at=r["confirm_notified_at"],
        label=r["label"],
    )


def _search(r: Row) -> Search:
    return Search(
        id=str(r["id"]),
        seeker_id=r["seeker_id"],
        topic_raw=r["topic_raw"],
        course_code=r["course_code"],
        subject=r["subject"],
        keywords=tuple(r["keywords"] or ()),
        label=r["label"],
        offered_group=Group(r["offered_group"]),
        status=SearchStatus(r["status"]),
        tried_session_ids=tuple(str(x) for x in (r["tried_session_ids"] or ())),
        created_at=r["created_at"],
        joined_at=r["joined_at"],
    )


def _request(r: Row) -> StudyRequest:
    return StudyRequest(
        id=str(r["id"]),
        search_id=str(r["search_id"]),
        seeker_id=r["seeker_id"],
        host_session_id=str(r["host_session_id"]),
        status=RequestStatus(r["status"]),
        created_at=r["created_at"],
        expires_at=r["expires_at"],
    )


def _match(r: Row) -> Match:
    return Match(
        id=str(r["id"]),
        request_id=str(r["request_id"]),
        seeker_id=r["seeker_id"],
        host_session_id=str(r["host_session_id"]),
        icebreaker=r["icebreaker"],
        card_key=r["card_key"],
        assigned_seat_id=r["assigned_seat_id"],
        status=MatchStatus(r["status"]),
        created_at=r["created_at"],
        expires_at=r["expires_at"],
        arrived_at=r["arrived_at"],
    )


class PostgresTx:
    """One transaction on one pooled connection."""

    def __init__(self, conn: Connection[TupleRow]) -> None:
        self._conn = conn

    def _all(self, query: str, params: Sequence[Any] | dict[str, Any] = ()) -> list[Row]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(query.encode(), params)
            return cur.fetchall()

    def _one(self, query: str, params: Sequence[Any] | dict[str, Any] = ()) -> Row | None:
        rows = self._all(query, params)
        return rows[0] if rows else None

    def _run(self, query: str, params: Sequence[Any] | dict[str, Any] = ()) -> None:
        self._conn.execute(query.encode(), params)

    def _insert(self, query: str, params: Sequence[Any] | dict[str, Any], rule: str) -> None:
        try:
            with self._conn.transaction():  # savepoint: a violation leaves the outer tx usable
                self._run(query, params)
        except psycopg.errors.UniqueViolation as exc:
            raise Conflict(rule) from exc

    # --- places --------------------------------------------------------------

    def buildings(self) -> list[Building]:
        rows = self._all("SELECT id, name, is_simulated, busyness, lat, lng FROM buildings")
        return [
            Building(r["id"], r["name"], r["is_simulated"], r["busyness"], r["lat"], r["lng"])
            for r in rows
        ]

    def tables(self, building_id: str | None = None) -> list[Table]:
        rows = self._all(
            "SELECT id, building_id, floor, label, x, y FROM tables"
            " WHERE %(b)s::text IS NULL OR building_id = %(b)s",
            {"b": building_id},
        )
        return [
            Table(r["id"], r["building_id"], r["floor"], r["label"], float(r["x"]), float(r["y"]))
            for r in rows
        ]

    def seats(self, building_id: str | None = None) -> list[Seat]:
        rows = self._all(
            f"SELECT {_SEAT_COLS} FROM seats s JOIN tables t ON t.id = s.table_id"
            " WHERE %(b)s::text IS NULL OR t.building_id = %(b)s",
            {"b": building_id},
        )
        return [_seat(r) for r in rows]

    def seat(self, seat_id: str) -> Seat | None:
        r = self._one(
            f"SELECT {_SEAT_COLS} FROM seats s JOIN tables t ON t.id = s.table_id WHERE s.id = %s",
            (seat_id,),
        )
        return _seat(r) if r else None

    # --- sensing -------------------------------------------------------------

    _STATE_COLS = (
        "seat_id, state, candidate_state, candidate_since, state_since, away_since,"
        " last_object, last_human, last_seen, blink_until"
    )

    def seat_states(self, seat_ids: Sequence[str]) -> dict[str, SeatState]:
        if not seat_ids:
            return {}
        rows = self._all(
            f"SELECT {self._STATE_COLS} FROM seat_state WHERE seat_id = ANY(%s)", (list(seat_ids),)
        )
        return {r["seat_id"]: _seat_state(r) for r in rows}

    def lock_seat_state(self, seat_id: str) -> SeatState | None:
        r = self._one(
            f"SELECT {self._STATE_COLS} FROM seat_state WHERE seat_id = %s FOR UPDATE", (seat_id,)
        )
        return _seat_state(r) if r else None

    def save_seat_state(self, state: SeatState) -> None:
        self._run(
            f"""INSERT INTO seat_state ({self._STATE_COLS})
                VALUES (%(seat_id)s, %(state)s, %(candidate_state)s, %(candidate_since)s,
                        %(state_since)s, %(away_since)s, %(last_object)s, %(last_human)s,
                        %(last_seen)s, %(blink_until)s)
                ON CONFLICT (seat_id) DO UPDATE SET
                  state = EXCLUDED.state, candidate_state = EXCLUDED.candidate_state,
                  candidate_since = EXCLUDED.candidate_since, state_since = EXCLUDED.state_since,
                  away_since = EXCLUDED.away_since, last_object = EXCLUDED.last_object,
                  last_human = EXCLUDED.last_human, last_seen = EXCLUDED.last_seen,
                  blink_until = EXCLUDED.blink_until""",
            {
                "seat_id": state.seat_id,
                "state": state.state.value,
                "candidate_state": state.candidate_state.value,
                "candidate_since": state.candidate_since,
                "state_since": state.state_since,
                "away_since": state.away_since,
                "last_object": state.last_object,
                "last_human": state.last_human,
                "last_seen": state.last_seen,
                "blink_until": state.blink_until,
            },
        )

    def touch_node(self, node_id: str, now: datetime) -> None:
        self._run("UPDATE nodes SET last_seen = %s WHERE id = %s", (now, node_id))

    def insert_readings(self, rows: Sequence[StoredReading]) -> None:
        with self._conn.cursor() as cur:
            cur.executemany(
                b"INSERT INTO seat_readings (time, seat_id, online, object_present, human_present)"
                b" VALUES (%s, %s, %s, %s, %s)",
                [(r.time, r.seat_id, r.online, r.object_present, r.human_present) for r in rows],
            )

    def readings(self, seat_ids: Sequence[str], until: datetime) -> list[StoredReading]:
        rows = self._all(
            "SELECT seat_id, time, online, object_present, human_present FROM seat_readings"
            " WHERE seat_id = ANY(%s) AND time < %s ORDER BY seat_id, time",
            (list(seat_ids), until),
        )
        return [
            StoredReading(
                r["seat_id"], r["time"], r["online"], r["object_present"], r["human_present"]
            )
            for r in rows
        ]

    # --- users and topics ----------------------------------------------------

    def user(self, user_id: str) -> User | None:
        r = self._one("SELECT id, first_name, is_demo FROM users WHERE id = %s", (user_id,))
        return User(r["id"], r["first_name"], r["is_demo"]) if r else None

    def demo_users(self) -> list[User]:
        rows = self._all(
            "SELECT id, first_name, is_demo FROM users WHERE is_demo ORDER BY first_name"
        )
        return [User(r["id"], r["first_name"], r["is_demo"]) for r in rows]

    def cached_topic(self, key: str) -> Topic | None:
        r = self._one(
            "SELECT course_code, subject, keywords, label FROM topic_cache WHERE text_key = %s",
            (key,),
        )
        return (
            Topic(r["course_code"], r["subject"], tuple(r["keywords"]), r["label"]) if r else None
        )

    def cache_topic(self, key: str, topic: Topic) -> None:
        self._run(
            "INSERT INTO topic_cache (text_key, course_code, subject, keywords, label)"
            " VALUES (%s, %s, %s, %s, %s) ON CONFLICT (text_key) DO NOTHING",
            (key, topic.course_code, topic.subject, list(topic.keywords), topic.label),
        )

    # --- host sessions -------------------------------------------------------

    _SESSION_COLS = (
        "id, user_id, seat_id, topic_raw, course_code, subject, keywords, label, about_me, open,"
        " muted, started_at, expires_at, ended_at, end_reason, confirm_notified_at"
    )

    def _session_params(self, s: HostSession) -> dict[str, Any]:
        return {
            "id": s.id, "user_id": s.user_id, "seat_id": s.seat_id, "topic_raw": s.topic_raw,
            "course_code": s.course_code, "subject": s.subject, "keywords": list(s.keywords),
            "label": s.label, "about_me": s.about_me, "open": s.open, "muted": s.muted,
            "started_at": s.started_at, "expires_at": s.expires_at, "ended_at": s.ended_at,
            "end_reason": s.end_reason.value if s.end_reason else None,
            "confirm_notified_at": s.confirm_notified_at,
        }  # fmt: skip

    def insert_session(self, session: HostSession) -> None:
        self._insert(
            f"""INSERT INTO host_sessions ({self._SESSION_COLS}) VALUES (
                %(id)s, %(user_id)s, %(seat_id)s, %(topic_raw)s, %(course_code)s, %(subject)s,
                %(keywords)s, %(label)s, %(about_me)s, %(open)s, %(muted)s, %(started_at)s,
                %(expires_at)s, %(ended_at)s, %(end_reason)s, %(confirm_notified_at)s)""",
            self._session_params(session),
            "one live session per user and per seat",
        )

    def update_session(self, session: HostSession) -> None:
        self._run(
            """UPDATE host_sessions SET topic_raw = %(topic_raw)s, course_code = %(course_code)s,
                 subject = %(subject)s, keywords = %(keywords)s, label = %(label)s,
                 about_me = %(about_me)s, open = %(open)s, muted = %(muted)s,
                 expires_at = %(expires_at)s, ended_at = %(ended_at)s, end_reason = %(end_reason)s,
                 confirm_notified_at = %(confirm_notified_at)s
               WHERE id = %(id)s""",
            self._session_params(session),
        )

    def session(self, session_id: str, lock: Lock = Lock.NONE) -> HostSession | None:
        sid = _uuid(session_id)
        if sid is None:
            return None
        r = self._one(
            f"SELECT {self._SESSION_COLS} FROM host_sessions WHERE id = %s{_LOCK_SQL[lock]}", (sid,)
        )
        return _session(r) if r else None

    def live_session_for_user(self, user_id: str, lock: Lock = Lock.NONE) -> HostSession | None:
        r = self._one(
            f"SELECT {self._SESSION_COLS} FROM host_sessions"
            f" WHERE user_id = %s AND ended_at IS NULL{_LOCK_SQL[lock]}",
            (user_id,),
        )
        return _session(r) if r else None

    def live_sessions(self) -> list[HostSession]:
        rows = self._all(f"SELECT {self._SESSION_COLS} FROM host_sessions WHERE ended_at IS NULL")
        return [_session(r) for r in rows]

    def live_sessions_for_seats(self, seat_ids: Sequence[str]) -> list[HostSession]:
        if not seat_ids:
            return []
        rows = self._all(
            f"SELECT {self._SESSION_COLS} FROM host_sessions"
            " WHERE ended_at IS NULL AND seat_id = ANY(%s)",
            (list(seat_ids),),
        )
        return [_session(r) for r in rows]

    # --- searches and requests -----------------------------------------------

    _SEARCH_COLS = (
        "id, seeker_id, topic_raw, course_code, subject, keywords, label, offered_group, status,"
        " tried_session_ids, created_at, joined_at"
    )

    def _search_params(self, s: Search) -> dict[str, Any]:
        return {
            "id": s.id, "seeker_id": s.seeker_id, "topic_raw": s.topic_raw,
            "course_code": s.course_code, "subject": s.subject, "keywords": list(s.keywords),
            "label": s.label, "offered_group": s.offered_group.value, "status": s.status.value,
            "tried": list(s.tried_session_ids), "created_at": s.created_at,
            "joined_at": s.joined_at,
        }  # fmt: skip

    def insert_search(self, search: Search) -> None:
        self._insert(
            f"""INSERT INTO searches ({self._SEARCH_COLS}) VALUES (%(id)s, %(seeker_id)s,
                %(topic_raw)s, %(course_code)s, %(subject)s, %(keywords)s, %(label)s,
                %(offered_group)s, %(status)s, %(tried)s::uuid[], %(created_at)s, %(joined_at)s)""",
            self._search_params(search),
            "one active search per seeker",
        )

    def update_search(self, search: Search) -> None:
        self._run(
            """UPDATE searches SET status = %(status)s, tried_session_ids = %(tried)s::uuid[],
                 joined_at = %(joined_at)s WHERE id = %(id)s""",
            self._search_params(search),
        )

    def search(self, search_id: str, lock: Lock = Lock.NONE) -> Search | None:
        sid = _uuid(search_id)
        if sid is None:
            return None
        r = self._one(
            f"SELECT {self._SEARCH_COLS} FROM searches WHERE id = %s{_LOCK_SQL[lock]}", (sid,)
        )
        return _search(r) if r else None

    def active_search_for_user(self, user_id: str) -> Search | None:
        r = self._one(
            f"SELECT {self._SEARCH_COLS} FROM searches WHERE seeker_id = %s AND status = 'active'",
            (user_id,),
        )
        return _search(r) if r else None

    _REQUEST_COLS = "id, search_id, seeker_id, host_session_id, status, created_at, expires_at"

    def insert_request(self, request: StudyRequest) -> None:
        self._insert(
            f"INSERT INTO requests ({self._REQUEST_COLS}) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                request.id, request.search_id, request.seeker_id, request.host_session_id,
                request.status.value, request.created_at, request.expires_at,
            ),
            "one pending request per search",
        )  # fmt: skip

    def update_request(self, request: StudyRequest) -> None:
        self._run(
            "UPDATE requests SET status = %s WHERE id = %s", (request.status.value, request.id)
        )

    def request(self, request_id: str, lock: Lock = Lock.NONE) -> StudyRequest | None:
        rid = _uuid(request_id)
        if rid is None:
            return None
        r = self._one(
            f"SELECT {self._REQUEST_COLS} FROM requests WHERE id = %s{_LOCK_SQL[lock]}", (rid,)
        )
        return _request(r) if r else None

    def pending_request_for_search(self, search_id: str) -> StudyRequest | None:
        r = self._one(
            f"SELECT {self._REQUEST_COLS} FROM requests"
            " WHERE search_id = %s AND status = 'pending'",
            (search_id,),
        )
        return _request(r) if r else None

    def pending_requests_for_session(self, session_id: str) -> list[StudyRequest]:
        rows = self._all(
            f"SELECT {self._REQUEST_COLS} FROM requests"
            " WHERE host_session_id = %s AND status = 'pending' ORDER BY created_at, id",
            (session_id,),
        )
        return [_request(r) for r in rows]

    def count_requests_since(self, seeker_id: str, since: datetime) -> int:
        r = self._one(
            "SELECT count(*) AS n FROM requests WHERE seeker_id = %s AND created_at >= %s",
            (seeker_id, since),
        )
        return int(r["n"]) if r else 0

    # --- matches -------------------------------------------------------------

    _MATCH_COLS = (
        "id, request_id, seeker_id, host_session_id, icebreaker, card_key, assigned_seat_id,"
        " status, created_at, expires_at, arrived_at"
    )

    def insert_match(self, match: Match) -> None:
        self._insert(
            f"INSERT INTO matches ({self._MATCH_COLS})"
            " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                match.id, match.request_id, match.seeker_id, match.host_session_id,
                match.icebreaker, match.card_key, match.assigned_seat_id, match.status.value,
                match.created_at, match.expires_at, match.arrived_at,
            ),
            "one active match per host session and per seeker",
        )  # fmt: skip

    def update_match(self, match: Match) -> None:
        self._run(
            "UPDATE matches SET status = %s, arrived_at = %s WHERE id = %s",
            (match.status.value, match.arrived_at, match.id),
        )

    def match(self, match_id: str, lock: Lock = Lock.NONE) -> Match | None:
        mid = _uuid(match_id)
        if mid is None:
            return None
        r = self._one(
            f"SELECT {self._MATCH_COLS} FROM matches WHERE id = %s{_LOCK_SQL[lock]}", (mid,)
        )
        return _match(r) if r else None

    def active_match_for_session(self, session_id: str) -> Match | None:
        r = self._one(
            f"SELECT {self._MATCH_COLS} FROM matches"
            " WHERE host_session_id = %s AND status = 'active'",
            (session_id,),
        )
        return _match(r) if r else None

    def active_match_for_seeker(self, user_id: str) -> Match | None:
        r = self._one(
            f"SELECT {self._MATCH_COLS} FROM matches WHERE seeker_id = %s AND status = 'active'",
            (user_id,),
        )
        return _match(r) if r else None

    def match_for_search(self, search_id: str) -> Match | None:
        r = self._one(
            f"""SELECT {", ".join("m." + c.strip() for c in self._MATCH_COLS.split(","))}
                FROM matches m JOIN requests r ON r.id = m.request_id
                WHERE r.search_id = %s AND r.status = 'accepted'""",
            (search_id,),
        )
        return _match(r) if r else None

    # --- safety --------------------------------------------------------------

    def insert_block(self, user_id: str, blocked_user_id: str) -> None:
        self._run(
            "INSERT INTO blocks (user_id, blocked_user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_id, blocked_user_id),
        )

    def blocked_with(self, user_id: str) -> set[str]:
        rows = self._all(
            "SELECT blocked_user_id AS other FROM blocks WHERE user_id = %(u)s"
            " UNION SELECT user_id FROM blocks WHERE blocked_user_id = %(u)s",
            {"u": user_id},
        )
        return {r["other"] for r in rows}

    def insert_report(self, reporter_id: str, reported_id: str, reason: str, now: datetime) -> None:
        self._run(
            "INSERT INTO reports (reporter_id, reported_id, reason, created_at)"
            " VALUES (%s, %s, %s, %s)",
            (reporter_id, reported_id, reason, now),
        )

    # --- push ----------------------------------------------------------------

    def upsert_subscription(
        self, user_id: str, endpoint: str, p256dh: str, auth: str, now: datetime
    ) -> None:
        self._run(
            """INSERT INTO push_subscriptions (user_id, endpoint, p256dh, auth, created_at)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (endpoint) DO UPDATE SET user_id = EXCLUDED.user_id,
                 p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth""",
            (user_id, endpoint, p256dh, auth, now),
        )

    def delete_subscription(self, endpoint: str, user_id: str | None = None) -> None:
        self._run(
            "DELETE FROM push_subscriptions"
            " WHERE endpoint = %s AND (%s::text IS NULL OR user_id = %s)",
            (endpoint, user_id, user_id),
        )

    def subscriptions_for(self, user_id: str) -> list[PushSubscription]:
        rows = self._all(
            "SELECT endpoint, p256dh, auth FROM push_subscriptions WHERE user_id = %s ORDER BY id",
            (user_id,),
        )
        return [_Subscription(r["endpoint"], r["p256dh"], r["auth"]) for r in rows]

    def enqueue(self, messages: Sequence[OutboxMessage], now: datetime) -> None:
        if not messages:
            return
        with self._conn.cursor() as cur:
            cur.executemany(
                b"INSERT INTO notification_outbox (user_id, kind, payload, created_at)"
                b" VALUES (%s, %s, %s::jsonb, %s)",
                [(m.user_id, m.kind.value, json.dumps(m.payload), now) for m in messages],
            )

    def claim_outbox(self, limit: int) -> list[_OutboxRow]:
        rows = self._all(
            """SELECT id, user_id, kind, payload, attempts FROM notification_outbox
               WHERE sent_at IS NULL ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED""",
            (limit,),
        )
        return [
            _OutboxRow(
                r["id"],
                OutboxMessage(r["user_id"], OutboxKind(r["kind"]), dict(r["payload"])),
                r["attempts"],
            )
            for r in rows
        ]

    def mark_outbox(self, row_id: int, sent_at: datetime | None, attempts: int) -> None:
        self._run(
            "UPDATE notification_outbox SET sent_at = %s, attempts = %s WHERE id = %s",
            (sent_at, attempts, row_id),
        )

    # --- scheduler -----------------------------------------------------------

    def due_search_ids(self, now: datetime, human_fresh_before: datetime) -> list[str]:
        rows = self._all(
            """SELECT DISTINCT r.search_id FROM requests r
               JOIN host_sessions h ON h.id = r.host_session_id
               LEFT JOIN seat_state ss ON ss.seat_id = h.seat_id
               WHERE r.status = 'pending'
                 AND (r.expires_at <= %(now)s OR h.ended_at IS NOT NULL
                      OR ss.last_human IS NULL OR ss.last_human < %(fresh)s)
               ORDER BY 1""",
            {"now": now, "fresh": human_fresh_before},
        )
        return [str(r["search_id"]) for r in rows]

    def due_match_ids(self, now: datetime, host_absent_before: datetime) -> list[str]:
        rows = self._all(
            """SELECT m.id FROM matches m JOIN host_sessions h ON h.id = m.host_session_id
               LEFT JOIN seat_state ss ON ss.seat_id = h.seat_id
               WHERE m.status = 'active'
                 AND (m.expires_at <= %(now)s OR ss.last_human IS NULL
                      OR ss.last_human < %(before)s)
               ORDER BY 1""",
            {"now": now, "before": host_absent_before},
        )
        return [str(r["id"]) for r in rows]

    def due_session_ids(self, now: datetime, host_absent_before: datetime) -> list[str]:
        rows = self._all(
            """SELECT h.id FROM host_sessions h JOIN seats s ON s.id = h.seat_id
               LEFT JOIN seat_state ss ON ss.seat_id = h.seat_id
               WHERE h.ended_at IS NULL AND NOT s.is_simulated
                 AND (h.expires_at <= %(now)s OR ss.last_human IS NULL
                      OR ss.last_human < %(before)s)
               ORDER BY 1""",
            {"now": now, "before": host_absent_before},
        )
        return [str(r["id"]) for r in rows]


@contextmanager
def _unavailable_on_connection_failure() -> Iterator[None]:
    """Connection-level failures become the port's `Unavailable` (503), never a 500 with
    driver details. Query errors (bad SQL, constraint violations) are not caught here."""
    try:
        yield
    except psycopg.OperationalError as exc:  # PoolTimeout and lost connections included
        log.warning("database unavailable: %s", type(exc).__name__)
        raise Unavailable from exc


class PostgresRepository:
    def __init__(
        self, url: str, read_url: str | None = None, *, pool_size: int, timeout_s: float = 5.0
    ) -> None:
        self._primary = make_pool(url, max_size=pool_size, timeout_s=timeout_s, name="primary")
        self._replica: ConnectionPool[BoundedConnection] | None = (
            make_pool(read_url, max_size=pool_size, timeout_s=timeout_s, name="replica")
            if read_url
            else None
        )

    def close(self) -> None:
        self._primary.close()
        if self._replica is not None:
            self._replica.close()

    @contextmanager
    def tx(self) -> Iterator[PostgresTx]:
        with (
            _unavailable_on_connection_failure(),
            self._primary.connection() as conn,
            conn.transaction(),
        ):
            yield PostgresTx(conn)

    @contextmanager
    def read(self) -> Iterator[PostgresTx]:
        """Read-only work; served by the replica when DATABASE_READ_URL is set (D32)."""
        pool = self._replica or self._primary
        with _unavailable_on_connection_failure(), pool.connection() as conn, conn.transaction():
            conn.execute(b"SET TRANSACTION READ ONLY")
            yield PostgresTx(conn)

    def ping(self) -> bool:
        try:
            with self._primary.connection(timeout=2) as conn:
                conn.execute(b"SELECT 1")
            return True
        except (psycopg.Error, TimeoutError, psycopg.OperationalError) as exc:
            log.warning("database ping failed: %s", type(exc).__name__)
            return False

    def history(
        self, building_id: str, since: datetime, until: datetime, offline: timedelta
    ) -> list[tuple[datetime, float]]:
        pool = self._replica or self._primary
        params = {"building": building_id, "since": since, "until": until, "offline": offline}
        with _unavailable_on_connection_failure(), pool.connection() as conn, conn.cursor() as cur:
            cur.execute(HISTORY_SQL.encode(), params)
            return [(hour, float(avg)) for hour, avg in cur.fetchall()]
