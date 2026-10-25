"""Wiring honors the connection budget (DB_POOL_SIZE) on real Postgres."""

from __future__ import annotations

import pytest

from app.adapters.repo_postgres import PostgresRepository
from app.wiring import build_services
from tests.conftest import make_settings
from tests.pg import db_url_for_tests

pytestmark = pytest.mark.db


def test_pool_size_comes_from_config() -> None:
    url = db_url_for_tests()
    if url is None:
        pytest.skip("TEST_DATABASE_URL not set")
    services = build_services(make_settings(database_url=url, db_pool_size=3))
    repo = services.ctx.repo
    assert isinstance(repo, PostgresRepository)
    try:
        assert repo._primary.max_size == 3
    finally:
        repo.close()


def test_pool_size_is_bounded() -> None:
    from pydantic import ValidationError

    for bad in (0, 51):
        with pytest.raises(ValidationError):
            make_settings(db_pool_size=bad)
