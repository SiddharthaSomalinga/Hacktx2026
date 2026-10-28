"""The Postgres hint feed (D61): delivery, reconnecting after a lost connection, idle periods."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator

import anyio
import psycopg
import pytest

from app.adapters.repo_postgres import FEED_APPLICATION_NAME, PostgresRepository
from app.domain.types import UserChange
from app.services.ports import Hint, Lost, Resync, UserHint
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


async def next_hint(feed: AsyncIterator[Hint], within: float = 5.0) -> Hint:
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
                b" WHERE application_name = %s",
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
