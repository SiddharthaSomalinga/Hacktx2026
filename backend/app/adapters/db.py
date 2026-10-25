"""Connection pools: one for the primary, and one for the read replica when configured (D32).

Every wait on the database is bounded by `timeout_s` (D35, D41): waiting for a pooled
connection, connecting, and each server round trip. A frozen or partitioned server keeps the
socket open and never replies, so without the round-trip bound a request would hang forever.
"""

from __future__ import annotations

import math

import psycopg
from psycopg import Connection
from psycopg.abc import PQGen
from psycopg.rows import TupleRow
from psycopg_pool import ConnectionPool


class BoundedConnection(Connection[TupleRow]):
    """A connection whose every server round trip (queries, BEGIN, COMMIT) has a deadline."""

    round_trip_timeout_s: float = 5.0

    def wait[RV](self, gen: PQGen[RV], interval: float = 0.1, timeout: float | None = None) -> RV:
        bound = self.round_trip_timeout_s if timeout is None else timeout
        try:
            return super().wait(gen, interval=interval, timeout=bound)
        except psycopg.OperationalError:
            # The protocol may be mid-message: close so the pool discards this connection.
            self.pgconn.finish()
            raise


def make_pool(
    url: str, *, max_size: int, timeout_s: float, name: str = "primary"
) -> ConnectionPool[BoundedConnection]:
    def configure(conn: BoundedConnection) -> None:
        conn.round_trip_timeout_s = timeout_s

    pool: ConnectionPool[BoundedConnection] = ConnectionPool(
        url,
        connection_class=BoundedConnection,
        min_size=1,
        max_size=max_size,
        name=name,
        open=True,
        # libpq's connect_timeout is whole seconds, minimum 2.
        kwargs={"autocommit": False, "connect_timeout": max(2, math.ceil(timeout_s))},
        configure=configure,
        timeout=timeout_s,  # how long a request waits for a pooled connection before 503
    )
    return pool
