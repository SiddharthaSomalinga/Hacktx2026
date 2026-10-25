"""Timescale policies and the hourly rollup job on real Postgres (D32, D33, Q12)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import psycopg
import pytest

from app.adapters.history_sql import policy_statements
from tests.pg import db_url_for_tests, reset

pytestmark = pytest.mark.db


@pytest.fixture
def url() -> str:
    found = db_url_for_tests()
    if found is None:
        pytest.skip("TEST_DATABASE_URL not set")
    reset(found)
    return found


def test_policies_apply_and_are_idempotent(url: str) -> None:
    with psycopg.connect(url, autocommit=True) as conn:
        for _ in range(2):
            for statement in policy_statements(30, 30):
                conn.execute(statement.encode())
        jobs = conn.execute(
            b"SELECT proc_name, config FROM timescaledb_information.jobs"
            b" WHERE hypertable_name = 'seat_readings' OR proc_name = 'rollup_open_hourly'"
            b" ORDER BY proc_name"
        ).fetchall()
    names = [name for name, _ in jobs]
    assert names.count("rollup_open_hourly") == 1
    assert {"policy_compression", "policy_retention"} <= set(names)
    assert dict(jobs)["rollup_open_hourly"] == {"offline_s": 30}


def test_rollup_stores_completed_hours_matching_the_live_query(url: str) -> None:
    now = datetime.now(UTC)
    two_hours_ago = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(
            b"INSERT INTO seat_readings VALUES (%s, 's1', true, false, false)", (two_hours_ago,)
        )
        conn.execute(b"UPDATE seat_state SET last_seen = %s WHERE seat_id = 's1'", (now,))
        conn.execute(b"CALL rollup_open_hourly(0, '{\"offline_s\": 30}')")
        conn.execute(b"CALL rollup_open_hourly(0, '{\"offline_s\": 30}')")  # idempotent
        stored = conn.execute(
            b"SELECT hour, open_avg FROM building_open_hourly WHERE building_id = 'lib'"
            b" AND hour >= %s ORDER BY hour",
            (two_hours_ago,),
        ).fetchall()
        live = conn.execute(
            b"SELECT hour, open_avg FROM open_hourly('lib', %s, %s, interval '30 seconds')",
            (two_hours_ago, two_hours_ago + timedelta(hours=2)),
        ).fetchall()
    assert stored == live
    assert [round(avg, 6) for _, avg in stored] == [1.0, 1.0]  # s1 open both completed hours
