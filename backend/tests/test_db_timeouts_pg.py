"""D35 under a hung database: the connection stays open but the server never answers.

A stopped database refuses connections and fails fast. A frozen or partitioned one accepts the
bytes and never replies, so only a client-side bound turns it into a 503. The proxy below
forwards to TEST_DATABASE_URL until frozen, then holds every byte without closing anything.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pytest

from app.adapters.repo_postgres import PostgresRepository
from app.services.ports import Unavailable
from tests.pg import db_url_for_tests, reset

pytestmark = pytest.mark.db

BOUND_S = 8.0  # the 5 s default bound plus slack for a loaded test machine


class FreezableProxy:
    def __init__(self, upstream: tuple[str, int]) -> None:
        self.upstream = upstream
        self.frozen = threading.Event()
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.port = self.listener.getsockname()[1]
        self.sockets: list[socket.socket] = []
        self.lock = threading.Lock()
        self.closed = False
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self) -> None:
        while True:
            try:
                client, _ = self.listener.accept()
                server = socket.create_connection(self.upstream)
            except OSError:
                return
            with self.lock:
                if self.closed:
                    client.close()
                    server.close()
                    return
                self.sockets += [client, server]
            for src, dst in ((client, server), (server, client)):
                threading.Thread(target=self._pump, args=(src, dst), daemon=True).start()

    def _pump(self, src: socket.socket, dst: socket.socket) -> None:
        try:
            while data := src.recv(65536):
                while self.frozen.is_set():  # hold the bytes: a server that never replies
                    time.sleep(0.05)
                dst.sendall(data)
        except OSError:
            pass
        finally:  # one side hung up: end the pair
            src.close()
            dst.close()

    def close(self) -> None:
        self.frozen.clear()
        with self.lock:
            self.closed = True
            for s in [self.listener, *self.sockets]:
                s.close()


def through(url: str, port: int) -> str:
    parts = urlsplit(url)
    creds = parts.netloc.rsplit("@", 1)[0]
    return urlunsplit(parts._replace(netloc=f"{creds}@127.0.0.1:{port}"))


@pytest.fixture
def frozen_db() -> Iterator[tuple[PostgresRepository, FreezableProxy]]:
    url = db_url_for_tests()
    if url is None:
        pytest.skip("TEST_DATABASE_URL not set")
    reset(url)
    parts = urlsplit(url)
    proxy = FreezableProxy((parts.hostname or "localhost", parts.port or 5432))
    repo = PostgresRepository(through(url, proxy.port), pool_size=2)
    try:
        yield repo, proxy
    finally:
        repo.close()  # before the proxy, so the pool does not reconnect through it
        proxy.close()


def bounded(call: Callable[[], Any]) -> tuple[float, Any]:
    """Runs `call` in a thread; fails the test instead of hanging it when `call` never returns."""
    outcome: dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["value"] = call()
        except Exception as exc:
            outcome["error"] = exc

    started = time.monotonic()
    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(BOUND_S)
    elapsed = time.monotonic() - started
    if thread.is_alive():
        pytest.fail(f"still blocked after {BOUND_S} s on a hung database")
    return elapsed, outcome.get("error", outcome.get("value"))


def read_buildings(repo: PostgresRepository) -> object:
    with repo.read() as tx:
        return tx.buildings()


def test_health_reports_a_hung_database_within_the_bound(
    frozen_db: tuple[PostgresRepository, FreezableProxy],
) -> None:
    repo, proxy = frozen_db
    assert repo.ping() is True
    proxy.frozen.set()
    elapsed, result = bounded(repo.ping)
    assert result is False
    assert elapsed < BOUND_S


def test_a_query_on_a_hung_database_is_unavailable_within_the_bound(
    frozen_db: tuple[PostgresRepository, FreezableProxy],
) -> None:
    repo, proxy = frozen_db
    assert read_buildings(repo)
    proxy.frozen.set()
    elapsed, result = bounded(lambda: read_buildings(repo))
    assert isinstance(result, Unavailable)
    assert elapsed < BOUND_S
    proxy.frozen.clear()
    _, recovered = bounded(lambda: read_buildings(repo))
    assert recovered and not isinstance(recovered, Exception)  # the stuck connection was dropped
