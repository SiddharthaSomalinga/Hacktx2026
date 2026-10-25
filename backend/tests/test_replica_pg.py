"""D32 read/write split: every write and lock goes to the primary, reads may use the replica.

The "replica" here is the same database reached through a role that can only SELECT, so any
write or row lock sent over the read pool fails loudly with permission denied.
"""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import urlsplit, urlunsplit

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


def reader_url(url: str) -> str:
    parts = urlsplit(url)
    host = parts.netloc.split("@", 1)[1]
    return urlunsplit(parts._replace(netloc=f"gs_reader:reader@{host}"))


@pytest.fixture
def split_repo() -> Iterator[tuple[PostgresRepository, FakeClock]]:
    url = db_url_for_tests()
    if url is None:
        pytest.skip("TEST_DATABASE_URL not set")
    reset(url)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(b"DROP OWNED BY gs_reader") if conn.execute(
            b"SELECT 1 FROM pg_roles WHERE rolname = 'gs_reader'"
        ).fetchone() else conn.execute(b"CREATE ROLE gs_reader LOGIN PASSWORD 'reader'")
        conn.execute(b"GRANT USAGE ON SCHEMA public TO gs_reader")
        conn.execute(b"GRANT SELECT ON ALL TABLES IN SCHEMA public TO gs_reader")
        conn.execute(b"GRANT EXECUTE ON FUNCTION open_hourly TO gs_reader")
    repo = PostgresRepository(url, reader_url(url), pool_size=4)
    try:
        yield repo, FakeClock()
    finally:
        repo.close()


def test_whole_flow_runs_with_a_select_only_replica(
    split_repo: tuple[PostgresRepository, FakeClock],
) -> None:
    repo, clock = split_repo
    settings = make_settings(map_cache_s=0)
    ctx = Context(
        repo=repo, ai=FallbackAI(), notifier=FakeNotifier(), clock=clock,
        timers=settings.timers(), map_cache_s=0, history_window_h=24, push_max_attempts=5,
        vapid_public_key="k",
    )  # fmt: skip
    services = Services.build(ctx)
    app = create_app(settings, services)
    node = Node(app, clock)
    node.set("s1", PERSON)
    node.post()
    alex, priya = Phone(app, "alex"), Phone(app, "priya")
    alex.ok("POST", "/api/host/link", {"seat_id": "s1"})
    alex.ok("POST", "/api/host/topic", {"topic_raw": "orgo 1"})
    sid = priya.ok("POST", "/api/search", {"topic_raw": "orgo 1"})["search_id"]
    priya.ok("POST", f"/api/search/{sid}/join")
    rid = alex.ok("GET", "/api/host/inbox")[0]["request_id"]
    mid = alex.ok("POST", f"/api/requests/{rid}/accept")["match_id"]
    priya.ok("GET", f"/api/matches/{mid}")
    priya.ok("POST", f"/api/matches/{mid}/arrived")
    for path in ("/api/buildings", "/api/buildings/lib", "/api/recommend?building_id=lib",
                 "/api/buildings/lib/history", "/api/me"):  # fmt: skip
        alex.ok("GET", path)
    node.set("s1", BAG)
    node.run(600)
    services.scheduler.tick()
    services.push.drain()
    assert alex.ok("GET", "/api/me")["host"] is None


def test_the_read_pool_really_cannot_write(
    split_repo: tuple[PostgresRepository, FakeClock],
) -> None:
    repo, _ = split_repo
    with pytest.raises(psycopg.errors.InsufficientPrivilege), repo._replica.connection() as conn:  # type: ignore[union-attr]
        conn.execute(b"UPDATE seat_state SET last_seen = now()")


def test_reads_are_served_by_the_replica_and_writes_by_the_primary(
    split_repo: tuple[PostgresRepository, FakeClock],
) -> None:
    repo, _ = split_repo
    with repo.read() as tx:
        assert tx._one("SELECT current_user AS u") == {"u": "gs_reader"}
    with repo.tx() as tx:
        assert tx._one("SELECT current_user AS u") == {"u": "postgres"}
