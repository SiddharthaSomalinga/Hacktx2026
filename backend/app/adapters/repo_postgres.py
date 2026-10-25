"""PostgresRepository: every SQL statement in the backend lives in this file (ARCH §3)."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import Connection
from psycopg.rows import TupleRow
from psycopg_pool import ConnectionPool

from app.adapters.db import make_pool

log = logging.getLogger("ghostseats.repo")


class PostgresTx:
    """One transaction on one pooled connection."""

    def __init__(self, conn: Connection[TupleRow]) -> None:
        self._conn = conn


class PostgresRepository:
    def __init__(self, url: str, read_url: str | None = None, *, pool_size: int = 10) -> None:
        self._primary = make_pool(url, max_size=pool_size, name="primary")
        self._replica: ConnectionPool[Connection[TupleRow]] | None = (
            make_pool(read_url, max_size=pool_size, name="replica") if read_url else None
        )

    def close(self) -> None:
        self._primary.close()
        if self._replica is not None:
            self._replica.close()

    @contextmanager
    def tx(self) -> Iterator[PostgresTx]:
        with self._primary.connection() as conn, conn.transaction():
            yield PostgresTx(conn)

    @contextmanager
    def read(self) -> Iterator[PostgresTx]:
        pool = self._replica or self._primary
        with pool.connection() as conn, conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            yield PostgresTx(conn)

    def ping(self) -> bool:
        try:
            with self._primary.connection(timeout=2) as conn:
                conn.execute("SELECT 1")
            return True
        except (psycopg.Error, TimeoutError) as exc:
            log.warning("database ping failed: %s", type(exc).__name__)
            return False
