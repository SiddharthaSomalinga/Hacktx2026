"""The demo flow and the concurrency guarantees against real Postgres (needs TEST_DATABASE_URL)."""

from __future__ import annotations

import threading
from collections.abc import Iterator

import psycopg
import pytest

from app.adapters.ai_fallback import FallbackAI
from app.adapters.repo_postgres import PostgresRepository
from app.main import create_app
from app.services.container import Services
from app.services.context import Context
from tests.api.harness import BAG, PERSON, Node, Phone
from tests.conftest import make_settings
from tests.fakes import FakeClock, FakeNotifier
from tests.pg import db_url_for_tests, reset

pytestmark = pytest.mark.db


@pytest.fixture
def pg() -> Iterator[tuple[Services, PostgresRepository, FakeClock, str]]:
    url = db_url_for_tests()
    if url is None:
        pytest.skip("TEST_DATABASE_URL not set")
    reset(url)
    repo = PostgresRepository(url, pool_size=12)
    clock = FakeClock()
    settings = make_settings(map_cache_s=0)
    ctx = Context(
        repo=repo,
        ai=FallbackAI(),
        notifier=FakeNotifier(),
        clock=clock,
        timers=settings.timers(),
        map_cache_s=0,
        history_window_h=24,
        push_max_attempts=5,
        vapid_public_key="k",
    )
    try:
        yield Services.build(ctx), repo, clock, url
    finally:
        repo.close()


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


def test_skip_locked_scheduler_ticks_do_not_collide(
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
    clock.advance(make_settings().request_timeout_s + 1)  # the first request expired; no polling
    node.post()

    barrier = threading.Barrier(6)

    def tick() -> None:
        barrier.wait()
        services.scheduler.tick()

    threads = [threading.Thread(target=tick) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    with psycopg.connect(url) as conn:
        statuses = sorted(
            s for (s,) in conn.execute(b"SELECT status FROM requests WHERE search_id = %s", (sid,))
        )
    assert statuses == ["expired", "pending"]  # one expiry, one new request, no duplicates
