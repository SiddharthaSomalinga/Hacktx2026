"""The demo flow and the concurrency guarantees against real Postgres (needs TEST_DATABASE_URL)."""

from __future__ import annotations

import threading
from collections.abc import Iterator, Mapping
from dataclasses import replace
from datetime import timedelta

import psycopg
import pytest

from app.adapters.ai_fallback import FallbackAI
from app.adapters.repo_postgres import PostgresRepository
from app.domain.types import OutboxKind, OutboxMessage, Reading, SeatChange
from app.main import create_app
from app.services.container import Services
from app.services.context import Context
from app.services.ports import Lock, PushResult, PushSubscription
from tests.api.harness import BAG, PERSON, Node, Phone
from tests.conftest import make_settings
from tests.fakes import FakeClock, FakeNotifier
from tests.pg import db_url_for_tests, reset
from tests.world import NODE

pytestmark = pytest.mark.db


@pytest.fixture
def pg() -> Iterator[tuple[Services, PostgresRepository, FakeClock, str]]:
    url = db_url_for_tests()
    if url is None:
        pytest.skip("TEST_DATABASE_URL not set")
    reset(url)
    repo = PostgresRepository(url, pool_size=12)
    clock = FakeClock()
    try:
        yield _services(repo, clock, FakeNotifier()), repo, clock, url
    finally:
        repo.close()


def _services(repo: PostgresRepository, clock: FakeClock, notifier: FakeNotifier) -> Services:
    ctx = Context(
        repo=repo,
        ai=FallbackAI(),
        notifier=notifier,
        clock=clock,
        timers=make_settings(map_cache_s=0).timers(),
        map_cache_s=0,
        history_window_h=24,
        push_max_attempts=5,
        vapid_public_key="k",
    )
    return Services.build(ctx)


def test_demo_flow_on_postgres(pg: tuple[Services, PostgresRepository, FakeClock, str]) -> None:
    services, _, clock, url = pg
    app = create_app(make_settings(map_cache_s=0), services)
    node = Node(app, clock)
    node.set("s1", PERSON)
    node.post()
    alex = Phone(app, "alex")
    alex.ok("POST", "/api/host/link", {"seat_id": "s1"})
    alex.ok("POST", "/api/host/topic", {"topic_raw": "ch 320m stereochem mechanisms"})
    priya = Phone(app, "priya")
    found = priya.ok("POST", "/api/search", {"topic_raw": "orgo 1 exam prep"})
    assert found["same_course"] == [{"building_id": "lib", "floor": 1, "count": 1}]
    priya.ok("POST", f"/api/search/{found['search_id']}/join")
    rid = alex.ok("GET", "/api/host/inbox")[0]["request_id"]
    mid = alex.ok("POST", f"/api/requests/{rid}/accept")["match_id"]
    assert node.post()["s1"] == "blue_blink"
    view = priya.ok("GET", f"/api/matches/{mid}")
    assert view["other_first_name"] == "Alex" and view["assigned_seat_id"] == "s2"
    assert priya.ok("POST", f"/api/matches/{mid}/arrived") == {"status": "completed"}
    node.set("s1", BAG)
    node.post()
    node.run(600)
    assert alex.ok("GET", "/api/me")["host"] is None  # D18 on Postgres too
    with psycopg.connect(url) as conn:
        kinds = [k for (k,) in conn.execute(b"SELECT kind FROM notification_outbox ORDER BY id")]
        rows = conn.execute(b"SELECT count(*) FROM seat_readings WHERE seat_id = 's1'").fetchone()
    assert kinds == ["request_received", "request_accepted", "session_ended"]
    assert rows is not None and rows[0] == 3  # change-only: person, bag... and the initial empty


def test_concurrent_advances_send_exactly_one_request(
    pg: tuple[Services, PostgresRepository, FakeClock, str],
) -> None:
    services, _, clock, url = pg
    app = create_app(make_settings(map_cache_s=0), services)
    node = Node(app, clock)
    for seat in ("s1", "s2", "s3"):
        node.set(seat, PERSON)
    node.post()
    for user, seat in (("alex", "s1"), ("jordan", "s2"), ("sam", "s3")):
        p = Phone(app, user)
        p.ok("POST", "/api/host/link", {"seat_id": seat})
        p.ok("POST", "/api/host/topic", {"topic_raw": "orgo 1"})
    priya = Phone(app, "priya")
    sid = priya.ok("POST", "/api/search", {"topic_raw": "orgo 1"})["search_id"]
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(b"UPDATE searches SET joined_at = now() WHERE id = %s", (sid,))

    barrier = threading.Barrier(8)
    errors: list[BaseException] = []

    def advance() -> None:
        try:
            barrier.wait()
            services.lifecycle.advance_search(sid)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=advance) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    with psycopg.connect(url) as conn:
        n = conn.execute(b"SELECT count(*) FROM requests WHERE search_id = %s", (sid,)).fetchone()
        tried = conn.execute(
            b"SELECT cardinality(tried_session_ids) FROM searches WHERE id = %s", (sid,)
        ).fetchone()
    assert n is not None and n[0] == 1
    assert tried is not None and tried[0] == 1


def test_concurrent_scheduler_ticks_do_not_collide(
    pg: tuple[Services, PostgresRepository, FakeClock, str],
) -> None:
    services, _, clock, url = pg
    app = create_app(make_settings(map_cache_s=0), services)
    node = Node(app, clock)
    for seat in ("s1", "s2"):
        node.set(seat, PERSON)
    node.post()
    for user, seat in (("alex", "s1"), ("jordan", "s2")):
        p = Phone(app, user)
        p.ok("POST", "/api/host/link", {"seat_id": seat})
        p.ok("POST", "/api/host/topic", {"topic_raw": "orgo 1"})
    priya = Phone(app, "priya")
    sid = priya.ok("POST", "/api/search", {"topic_raw": "orgo 1"})["search_id"]
    priya.ok("POST", f"/api/search/{sid}/join")
    _expire_pending_request(url, sid, clock)
    assert _request_statuses(url, sid) == ["pending"]

    barrier = threading.Barrier(6)

    def tick() -> None:
        barrier.wait()
        services.scheduler.tick()

    threads = [threading.Thread(target=tick) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # One expiry, one new request, no duplicates.
    assert _request_statuses(url, sid) == ["expired", "pending"]


def test_a_tick_skips_a_search_another_transaction_holds(
    pg: tuple[Services, PostgresRepository, FakeClock, str],
) -> None:
    """SKIP LOCKED keeps a tick from queueing behind a request handler (or another instance)
    that is advancing the same search; the row is left for a later tick."""
    services, repo, clock, url = pg
    app = create_app(make_settings(map_cache_s=0), services)
    node = Node(app, clock)
    for seat in ("s1", "s2"):
        node.set(seat, PERSON)
    node.post()
    for user, seat in (("alex", "s1"), ("jordan", "s2")):
        p = Phone(app, user)
        p.ok("POST", "/api/host/link", {"seat_id": seat})
        p.ok("POST", "/api/host/topic", {"topic_raw": "orgo 1"})
    priya = Phone(app, "priya")
    sid = priya.ok("POST", "/api/search", {"topic_raw": "orgo 1"})["search_id"]
    priya.ok("POST", f"/api/search/{sid}/join")
    _expire_pending_request(url, sid, clock)

    ticked = threading.Event()

    def tick() -> None:
        services.scheduler.tick()
        ticked.set()

    with repo.tx() as tx:
        assert tx.search(sid, Lock.WAIT) is not None
        thread = threading.Thread(target=tick)
        thread.start()
        assert ticked.wait(1.0)  # the tick did not wait for this transaction
        assert _request_statuses(url, sid) == ["pending"]  # and left the search alone
    thread.join()
    services.scheduler.tick()
    assert _request_statuses(url, sid) == ["expired", "pending"]


def _expire_pending_request(url: str, search_id: str, clock: FakeClock) -> None:
    """Makes the pending request due while its host is still present. Advancing the clock
    instead needs a node post to keep the host present, and that ingest advances the search
    itself (advance_session), so a tick would find nothing to do."""
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(
            b"UPDATE requests SET expires_at = %s WHERE search_id = %s AND status = 'pending'",
            (clock.now() - timedelta(seconds=1), search_id),
        )


def _request_statuses(url: str, search_id: str) -> list[str]:
    with psycopg.connect(url) as conn:
        rows = conn.execute(b"SELECT status FROM requests WHERE search_id = %s", (search_id,))
        return sorted(s for (s,) in rows)


class GatedNotifier(FakeNotifier):
    """Holds each thread's first send until every drain has claimed its rows, so the drains'
    claims are guaranteed to overlap instead of merely likely to."""

    def __init__(self, drains: int) -> None:
        super().__init__()
        self._gate = threading.Barrier(drains, timeout=5)
        self._seen = threading.local()

    def send(self, subscription: PushSubscription, payload: Mapping[str, str]) -> PushResult:
        if not getattr(self._seen, "first", False):
            self._seen.first = True
            self._gate.wait()
        return super().send(subscription, payload)


def test_concurrent_drains_send_each_notification_once(
    pg: tuple[Services, PostgresRepository, FakeClock, str],
) -> None:
    _, repo, clock, url = pg
    drains, per_drain = 4, 5
    notifier = GatedNotifier(drains)
    services = _services(repo, clock, notifier)
    with repo.tx() as tx:
        tx.upsert_subscription("alex", "https://push.example/alex", "p256dh", "auth", clock.now())
        tx.enqueue(
            [
                OutboxMessage("alex", OutboxKind.REQUEST_RECEIVED, {"n": str(i)})
                for i in range(drains * per_drain)
            ],
            clock.now(),
        )

    errors: list[BaseException] = []

    def drain() -> None:
        try:
            services.push.drain(limit=per_drain)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=drain) for _ in range(drains)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    sent = sorted(int(payload["n"]) for _, payload in notifier.sent)
    assert sent == list(range(drains * per_drain))  # every row once: none skipped, none twice
    with psycopg.connect(url) as conn:
        unsent = conn.execute(b"SELECT count(*) FROM notification_outbox WHERE sent_at IS NULL")
        row = unsent.fetchone()
    assert row is not None and row[0] == 0


def test_seat_lock_keeps_a_reading_and_a_concurrent_blink(
    pg: tuple[Services, PostgresRepository, FakeClock, str],
) -> None:
    """Accept and the match view set `blink_until` under the seat lock while ingest rewrites the
    same row. Without FOR UPDATE, the later commit overwrites the earlier one's change."""
    services, repo, clock, _ = pg
    locked = threading.Event()
    ingested = threading.Event()

    def ingest() -> None:
        locked.wait()
        services.readings.ingest(NODE, [Reading("s1", True, True)])
        ingested.set()

    thread = threading.Thread(target=ingest)
    thread.start()
    with repo.tx() as tx:  # the blink half of RequestService.accept
        state = tx.lock_seat_state("s1")
        assert state is not None
        locked.set()
        assert not ingested.wait(0.5)  # ingest is waiting on the seat lock
        tx.save_seat_state(
            replace(state, blink_until=clock.now() + timedelta(seconds=60)), change=SeatChange.NONE
        )
    thread.join(10)
    assert ingested.is_set()
    with repo.read() as tx:
        final = tx.seat_states(["s1"])["s1"]
    assert final.blink_until == clock.now() + timedelta(seconds=60)
    assert final.last_human == clock.now()
