from __future__ import annotations

from collections.abc import Iterator

import pytest

from app.adapters.repo_postgres import PostgresRepository
from app.services.ports import Repository
from tests.fakes import InMemoryRepository
from tests.pg import reset, test_database_url
from tests.world import build_world


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.db)])
def repo(request: pytest.FixtureRequest) -> Iterator[Repository]:
    """The same world in both implementations; every contract test runs against each."""
    if request.param == "memory":
        mem = InMemoryRepository()
        build_world(mem)
        yield mem
        return
    url = test_database_url()
    if url is None:
        pytest.skip("TEST_DATABASE_URL not set")
    reset(url)
    pg = PostgresRepository(url, pool_size=4)
    try:
        yield pg
    finally:
        pg.close()
