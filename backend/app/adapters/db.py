"""Connection pools: one for the primary, and one for the read replica when configured (D32)."""

from __future__ import annotations

from psycopg import Connection
from psycopg.rows import TupleRow
from psycopg_pool import ConnectionPool


def make_pool(
    url: str, *, max_size: int, name: str = "primary"
) -> ConnectionPool[Connection[TupleRow]]:
    pool: ConnectionPool[Connection[TupleRow]] = ConnectionPool(
        url,
        min_size=1,
        max_size=max_size,
        name=name,
        open=True,
        kwargs={"autocommit": False},
        timeout=10,
    )
    return pool
