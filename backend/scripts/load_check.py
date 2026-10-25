"""Load check (B5.4, D32): polling phones plus posting nodes against a running backend.

    uv run python -m scripts.load_check --base-url http://localhost:8000 --clients 500 --nodes 50

Nodes need real seats: `--setup` creates a "loadtest" building with `--nodes` nodes of 4 seats
each in DATABASE_URL (idempotent). Clients poll /api/buildings and /api/buildings/<id> every
POLL_WEB_S with If-None-Match, like the frontend. Prints p50/p95/max per endpoint and errors.
"""

from __future__ import annotations

import argparse
import asyncio
import multiprocessing
import os
import random
import statistics
import sys
import time
from collections import defaultdict

import httpx

LOAD_BUILDING = "loadtest"


def setup(nodes: int) -> None:
    import psycopg

    from app.config import get_settings

    with psycopg.connect(get_settings().database_url) as conn, conn.transaction():
        conn.execute(
            b"""INSERT INTO buildings (id, name, is_simulated, busyness, lat, lng)
                VALUES ('loadtest', 'Load Test Hall', false, 0, 30.28, -97.73)
                ON CONFLICT DO NOTHING"""
        )
        for n in range(nodes):
            node, table = f"load-n{n}", f"load-t{n}"
            conn.execute(b"INSERT INTO nodes (id) VALUES (%s) ON CONFLICT DO NOTHING", (node,))
            conn.execute(
                b"""INSERT INTO tables (id, building_id, floor, label, x, y)
                    VALUES (%s, 'loadtest', 1, %s, %s, %s) ON CONFLICT DO NOTHING""",
                (table, f"Table {n:02d}", (n % 10) * 10, (n // 10) * 10 % 100),
            )
            for p in range(1, 5):
                conn.execute(
                    b"""INSERT INTO seats (id, table_id, node_id, position, is_simulated)
                        VALUES (%s, %s, %s, %s, false) ON CONFLICT DO NOTHING""",
                    (f"{table}-s{p}", table, node, p),
                )
        conn.execute(
            b"""INSERT INTO seat_state (seat_id, state, candidate_state)
                SELECT id, 'open', 'open' FROM seats WHERE node_id LIKE 'load-n%%'
                ON CONFLICT DO NOTHING"""
        )
    print(f"set up {nodes} nodes x 4 seats in building {LOAD_BUILDING!r}")


def _int_counter() -> dict[int, int]:
    return defaultdict(int)  # module-level so Stats pickles across processes


def teardown() -> None:
    """Remove everything `setup` created, so the load test leaves no seats behind."""
    import psycopg

    from app.config import get_settings

    with psycopg.connect(get_settings().database_url) as conn, conn.transaction():
        seats = "SELECT id FROM seats WHERE node_id LIKE 'load-n%%'"
        conn.execute(f"DELETE FROM seat_readings WHERE seat_id IN ({seats})".encode())
        conn.execute(f"DELETE FROM seat_state WHERE seat_id IN ({seats})".encode())
        conn.execute(b"DELETE FROM seats WHERE node_id LIKE 'load-n%%'")
        conn.execute(b"DELETE FROM nodes WHERE id LIKE 'load-n%%'")
        conn.execute(b"DELETE FROM building_open_hourly WHERE building_id = 'loadtest'")
        conn.execute(b"DELETE FROM tables WHERE building_id = 'loadtest'")
        conn.execute(b"DELETE FROM buildings WHERE id = 'loadtest'")
    print(f"removed the {LOAD_BUILDING!r} load-test data")


class Stats:
    def __init__(self) -> None:
        self.latency: dict[str, list[float]] = defaultdict(list)
        self.status: dict[str, dict[int, int]] = defaultdict(_int_counter)
        self.errors: dict[str, int] = defaultdict(int)

    def merge(self, other: Stats) -> None:
        for name, xs in other.latency.items():
            self.latency[name].extend(xs)
        for name, codes in other.status.items():
            for code, n in codes.items():
                self.status[name][code] += n
        for name, n in other.errors.items():
            self.errors[name] += n

    def record(self, name: str, started: float, response: httpx.Response | None) -> None:
        if response is None:
            self.errors[name] += 1
            return
        self.latency[name].append((time.perf_counter() - started) * 1000)
        self.status[name][response.status_code] += 1

    def report(self) -> str:
        lines = [f"{'endpoint':<22}{'n':>8}{'p50 ms':>10}{'p95 ms':>10}{'max ms':>10}  statuses"]
        for name in sorted(self.latency):
            xs = sorted(self.latency[name])
            p95 = xs[int(len(xs) * 0.95) - 1] if len(xs) >= 20 else xs[-1]
            codes = " ".join(f"{c}:{n}" for c, n in sorted(self.status[name].items()))
            p50 = statistics.median(xs)
            lines.append(f"{name:<22}{len(xs):>8}{p50:>10.1f}{p95:>10.1f}{xs[-1]:>10.1f}  {codes}")
        for name, n in sorted(self.errors.items()):
            lines.append(f"{name:<22} transport errors: {n}")
        return "\n".join(lines)


async def timed(stats: Stats, name: str, call: object) -> httpx.Response | None:
    started = time.perf_counter()
    try:
        response = await call  # type: ignore[misc]
    except httpx.HTTPError:
        stats.record(name, started, None)
        return None
    stats.record(name, started, response)
    return response


async def phone(client: httpx.AsyncClient, stats: Stats, stop: float, poll_s: float) -> None:
    etags: dict[str, str] = {}
    await asyncio.sleep(random.uniform(0, poll_s))  # spread the herd
    while time.perf_counter() < stop:
        for path, name in (
            ("/api/buildings", "GET buildings"),
            ("/api/buildings/pcl", "GET building"),
        ):
            headers = {"If-None-Match": etags[path]} if path in etags else {}
            r = await timed(stats, name, client.get(path, headers=headers))
            if r is not None and r.status_code == 200:
                etags[path] = r.headers.get("etag", "")
        await asyncio.sleep(poll_s)


async def node(client: httpx.AsyncClient, stats: Stats, stop: float, n: int, key: str) -> None:
    seats = [f"load-t{n}-s{p}" for p in range(1, 5)]
    await asyncio.sleep(random.uniform(0, 2))
    while time.perf_counter() < stop:
        readings = [
            {
                "seat_id": s,
                "object_present": random.random() < 0.5,
                "human_present": random.random() < 0.4,
            }
            for s in seats
        ]
        await timed(
            stats,
            "POST readings",
            client.post(
                "/api/readings",
                json={"node_id": f"load-n{n}", "readings": readings},
                headers={"X-Node-Key": key},
            ),
        )
        await asyncio.sleep(2)


async def run(base_url: str, clients: int, nodes: range, seconds: float, poll_s: float) -> Stats:
    key = os.environ.get("NODE_KEY", "")
    stats = Stats()
    stop = time.perf_counter() + seconds
    limits = httpx.Limits(
        max_connections=clients + len(nodes), max_keepalive_connections=clients + len(nodes)
    )
    async with httpx.AsyncClient(base_url=base_url, limits=limits, timeout=10) as client:
        tasks = [phone(client, stats, stop, poll_s) for _ in range(clients)]
        tasks += [node(client, stats, stop, n, key) for n in nodes]
        await asyncio.gather(*tasks)
    return stats


def _run_part(base_url: str, clients: int, nodes: range, seconds: float, poll_s: float) -> Stats:
    return asyncio.run(run(base_url, clients, nodes, seconds, poll_s))


def node_key() -> str:
    """NODE_KEY from the environment, else from .env through the app's settings."""
    key = os.environ.get("NODE_KEY")
    if key:
        return key
    try:
        from app.config import get_settings

        return get_settings().node_key.get_secret_value()
    except Exception:
        return ""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--clients", type=int, default=500)
    parser.add_argument("--nodes", type=int, default=50)
    parser.add_argument("--seconds", type=float, default=60)
    parser.add_argument("--poll", type=float, default=3.0)
    parser.add_argument("--procs", type=int, default=4, help="generator processes")
    parser.add_argument(
        "--setup", action="store_true", help="create the load-test nodes first, remove them after"
    )
    args = parser.parse_args(argv)
    if args.nodes and not node_key():
        print("NODE_KEY must be set in the environment or .env", file=sys.stderr)
        return 2
    os.environ["NODE_KEY"] = node_key()  # generator processes read it from the environment
    if args.setup:
        setup(args.nodes)
    # One asyncio process saturates a core around 500 clients, which then measures the generator
    # rather than the backend; split the load across processes and merge the samples.
    jobs = [
        (
            args.base_url,
            len(range(i, args.clients, args.procs)),
            range(i, args.nodes, args.procs),
            args.seconds,
            args.poll,
        )
        for i in range(args.procs)
    ]
    try:
        with multiprocessing.Pool(args.procs) as pool:
            parts = pool.starmap(_run_part, jobs)
    finally:
        if args.setup:
            teardown()
    stats = Stats()
    for part in parts:
        stats.merge(part)
    print(
        f"{args.clients} clients, {args.nodes} nodes, {args.procs} generator processes,"
        f" {args.seconds:.0f} s against {args.base_url}"
    )
    print(stats.report())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
