"""The Postgres hint feed (D61): delivery, reconnecting after a lost connection, idle periods."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import anyio
import psycopg
import pytest

from app.adapters.clock import SystemClock
from app.adapters.repo_postgres import FEED_APPLICATION_NAME, PostgresRepository
from app.domain.types import UserChange
from app.services.ports import Lost, Resync, UserHint
from tests.pg import db_url_for_tests, reset
from tests.repo_contract.test_repository import new_session

pytestmark = [pytest.mark.db, pytest.mark.anyio]


@pytest.fixture
def url() -> Iterator[str]:
    found = db_url_for_tests()
    if found is None:
        pytest.skip("TEST_DATABASE_URL not set")
    reset(found)
    yield found


async def next_hint[T](feed: AsyncIterator[T], within: float = 5.0) -> T:
    with anyio.fail_after(within):
        return await anext(feed)


async def test_a_committed_write_reaches_the_feed(url: str) -> None:
    repo = PostgresRepository(url, pool_size=2, feed_probe_s=0.2)
    feed = repo.hints()
    try:
        assert isinstance(await next_hint(feed), Resync)
        with repo.tx() as tx:
            tx.insert_session(new_session())
        assert await next_hint(feed) == UserHint("alex", frozenset({UserChange.SESSION}))
    finally:
        await feed.aclose()
        repo.close()


async def test_idle_longer_than_the_probe_keeps_the_connection(url: str) -> None:
    """A wait bound on the listener's round trips would close it here (the pool's trap)."""
    repo = PostgresRepository(url, pool_size=2, timeout_s=1, feed_probe_s=0.2)
    feed = repo.hints()
    try:
        assert isinstance(await next_hint(feed), Resync)
        await anyio.sleep(1.5)  # several probe windows with no hints
        with repo.tx() as tx:
            tx.insert_session(new_session())
        assert isinstance(await next_hint(feed), UserHint)  # not a second Resync
    finally:
        await feed.aclose()
        repo.close()


async def test_a_killed_listener_reconnects_and_says_resync(url: str) -> None:
    repo = PostgresRepository(url, pool_size=2, timeout_s=1, feed_probe_s=0.2)
    feed = repo.hints()
    try:
        assert isinstance(await next_hint(feed), Resync)
        with psycopg.connect(url, autocommit=True) as admin:
            killed = admin.execute(
                b"SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity"
                b" WHERE application_name = %s AND datname = current_database()",
                (FEED_APPLICATION_NAME,),
            ).fetchone()
        assert killed == (1,)
        assert isinstance(await next_hint(feed), Lost)
        assert isinstance(await next_hint(feed), Resync)  # hints may have been missed
        with repo.tx() as tx:
            tx.insert_session(new_session())
        assert isinstance(await next_hint(feed), UserHint)
    finally:
        await feed.aclose()
        repo.close()


async def test_a_write_on_one_instance_reaches_a_stream_on_another(url: str) -> None:
    """Two instances share one database. B's periodic rebuild is 30 s away, so the change can
    only reach B's stream within a second through NOTIFY."""
    import json
    from datetime import timedelta

    import anyio.to_thread

    from app.adapters.ai_fallback import FallbackAI
    from app.domain.types import Reading
    from app.services.container import Services
    from app.services.context import Context
    from tests.conftest import make_settings
    from tests.fakes import FakeNotifier
    from tests.world import NODE

    settings = make_settings()

    def instance() -> tuple[Services, PostgresRepository]:
        repo = PostgresRepository(url, pool_size=2, feed_probe_s=5)
        ctx = Context(
            repo=repo,
            ai=FallbackAI(),
            notifier=FakeNotifier(),
            clock=SystemClock(),
            timers=settings.timers(),
            map_cache_s=0,
            history_window_h=settings.history_window_h,
            push_max_attempts=settings.push_max_attempts,
            vapid_public_key=settings.vapid_public_key,
            demo_accept=timedelta(seconds=5),
            live_check_s=30,
        )
        return Services.build(ctx), repo

    (a, repo_a), (b, repo_b) = instance(), instance()
    try:
        async with anyio.create_task_group() as tg:
            tg.start_soon(b.live.hub.run)
            with anyio.fail_after(5):
                while not b.live.hub.hints_ok:
                    await anyio.sleep(0.01)
            sub = await b.live.open(None, "lib", None)
            events = sub.events()
            kinds = [(await next_hint(events)).kind for _ in range(2)]
            assert kinds == ["buildings", "building"]
            await anyio.to_thread.run_sync(a.readings.ingest, NODE, [Reading("s1", True, True)])
            started = anyio.current_time()
            while (event := await next_hint(events, within=1.0)).kind != "building":
                pass
            assert anyio.current_time() - started < 1.0
            states = {
                s["id"]: s["state"]
                for f in json.loads(event.data)["floors"]
                for t in f["tables"]
                for s in t["seats"]
            }
            assert states["s1"] == "occupied"
            tg.cancel_scope.cancel()
    finally:
        repo_a.close()
        repo_b.close()
