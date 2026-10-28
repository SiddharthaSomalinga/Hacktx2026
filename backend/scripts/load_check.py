"""Load check (B5.4, D32, D61): phones plus posting nodes against a running backend.

    uv run python -m scripts.load_check --base-url http://localhost:8000 --clients 500 --nodes 50
    uv run python -m scripts.load_check --setup --mode sse --clients 2000 --procs 8

Nodes need real seats: `--setup` creates a "loadtest" building with `--nodes` nodes of 4 seats
each, plus a probe seat, in DATABASE_URL (idempotent), and removes them afterwards.

`--mode poll`: phones poll /api/buildings and /api/buildings/<building> every POLL_WEB_S with
If-None-Match, like the app without its stream. `--mode sse`: phones hold GET /api/live.

With `--setup`, a probe node flips its seat every 12 s. T0 is the receipt of the first readings
response whose LED shows the new state (the commit happened inside that request; its round
trip is printed as the bias bound), and each phone records when it first sees the new state.
"""

from __future__ import annotations

import argparse
import asyncio
import multiprocessing
import os
import random
import resource
import statistics
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field

import httpx

LOAD_BUILDING = "loadtest"
PROBE_NODE, PROBE_SEAT = "load-probe", "load-probe-s1"
PROBE_FLIP_S = 12.0
RAMP_S = 10.0  # phones connect over this long; the probe starts flipping after it
PERSON_LED = "red"  # occupied; open is green (FR-7)


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
        conn.execute(b"INSERT INTO nodes (id) VALUES (%s) ON CONFLICT DO NOTHING", (PROBE_NODE,))
        conn.execute(
            b"""INSERT INTO tables (id, building_id, floor, label, x, y)
                VALUES ('load-probe', 'loadtest', 1, 'Probe', 95, 95) ON CONFLICT DO NOTHING"""
        )
        conn.execute(
            b"""INSERT INTO seats (id, table_id, node_id, position, is_simulated)
                VALUES (%s, 'load-probe', %s, 1, false) ON CONFLICT DO NOTHING""",
            (PROBE_SEAT, PROBE_NODE),
        )
        conn.execute(
            b"""INSERT INTO seat_state (seat_id, state, candidate_state)
                SELECT id, 'open', 'open' FROM seats WHERE node_id LIKE 'load-%%'
                ON CONFLICT DO NOTHING"""
        )
    print(f"set up {nodes} nodes x 4 seats and a probe seat in building {LOAD_BUILDING!r}")


def _int_counter() -> dict[int, int]:
    return defaultdict(int)  # module-level so Stats pickles across processes


def teardown() -> None:
    """Remove everything `setup` created, so the load test leaves no seats behind."""
    import psycopg

    from app.config import get_settings

    with psycopg.connect(get_settings().database_url) as conn, conn.transaction():
        seats = "SELECT id FROM seats WHERE node_id LIKE 'load-%%'"
        conn.execute(f"DELETE FROM seat_readings WHERE seat_id IN ({seats})".encode())
        conn.execute(f"DELETE FROM seat_state WHERE seat_id IN ({seats})".encode())
        conn.execute(b"DELETE FROM seats WHERE node_id LIKE 'load-%%'")
        conn.execute(b"DELETE FROM nodes WHERE id LIKE 'load-%%'")
        conn.execute(b"DELETE FROM building_open_hourly WHERE building_id = 'loadtest'")
        conn.execute(b"DELETE FROM tables WHERE building_id = 'loadtest'")
        conn.execute(b"DELETE FROM buildings WHERE id = 'loadtest'")
    print(f"removed the {LOAD_BUILDING!r} load-test data")


@dataclass
class Seen:
    """What one phone saw of the probe seat: (monotonic time, state) at each change."""

    changes: list[tuple[float, str]] = field(default_factory=list)

    def saw(self, state: str) -> None:
        if not self.changes or self.changes[-1][1] != state:
            self.changes.append((time.monotonic(), state))


def merge_latency(
    flips: list[tuple[float, str]], phones: list[list[tuple[float, str]]]
) -> tuple[list[float], int]:
    """Seconds from each flip's T0 until each phone first showed the new state, and how many
    (flip, phone) pairs never did before the next flip. A phone may show a state a little before
    T0 (the commit precedes the response); those count as negative, never dropped."""
    delays: list[float] = []
    missed = 0
    for i, (t0, state) in enumerate(flips):
        until = flips[i + 1][0] if i + 1 < len(flips) else float("inf")
        for changes in phones:
            seen = [t for t, s in changes if s == state and t0 - 1.0 <= t < until]
            if seen:
                delays.append(seen[0] - t0)
            else:
                missed += 1
    return delays, missed


def _percentiles(xs: list[float]) -> str:
    xs = sorted(xs)
    if not xs:
        return "none"
    p95 = xs[int(len(xs) * 0.95) - 1] if len(xs) >= 20 else xs[-1]
    p50 = statistics.median(xs)
    return f"p50 {p50 * 1000:.0f} ms, p95 {p95 * 1000:.0f} ms, max {xs[-1] * 1000:.0f} ms"


class Stats:
    def __init__(self) -> None:
        self.latency: dict[str, list[float]] = defaultdict(list)
        self.status: dict[str, dict[int, int]] = defaultdict(_int_counter)
        self.errors: dict[str, int] = defaultdict(int)
        self.phones: list[list[tuple[float, str]]] = []
        self.flips: list[tuple[float, str]] = []
        self.probe_rtt: list[float] = []
        self.received = 0  # response body bytes, every phone
        self.requests = 0  # phone requests, streams included
        self.longest_gap: list[float] = []  # per stream: the longest silence between events
        self.first_event: list[float] = []  # per stream: connect to first event
        self.cpu_s = 0.0  # generator CPU, to tell a saturated generator from a slow server

    def merge(self, other: Stats) -> None:
        for name, xs in other.latency.items():
            self.latency[name].extend(xs)
        for name, codes in other.status.items():
            for code, n in codes.items():
                self.status[name][code] += n
        for name, n in other.errors.items():
            self.errors[name] += n
        self.phones += other.phones
        self.flips += other.flips
        self.probe_rtt += other.probe_rtt
        self.received += other.received
        self.requests += other.requests
        self.longest_gap += other.longest_gap
        self.first_event += other.first_event
        self.cpu_s += other.cpu_s

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

    def report_live(self, seconds: float, procs: int) -> str:
        lines = [
            f"phone requests: {self.requests} ({self.requests / seconds:.0f}/s);"
            f" received {self.received / seconds / 1024:.0f} KiB/s"
            f" ({self.received / max(len(self.phones), 1) / seconds:.0f} B/s per phone)",
            f"generator CPU: {self.cpu_s / seconds:.2f} cores over {procs} processes",
        ]
        if self.flips:
            delays, missed = merge_latency(self.flips, self.phones)
            lines.append(
                f"probe flips: {len(self.flips)}; change seen after {_percentiles(delays)};"
                f" missed {missed} of {len(self.flips) * len(self.phones)}"
                f" (probe round trip {_percentiles(self.probe_rtt)})"
            )
        if self.longest_gap:
            lines.append(f"streams: first event {_percentiles(self.first_event)}")
            lines.append(f"streams: longest silence {_percentiles(self.longest_gap)}")
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


_PROBE = f'"id":"{PROBE_SEAT}","position":1,"state":"'.encode()


def probe_state(body: bytes) -> str | None:
    """The probe seat's state, found by bytes rather than a JSON parse, so a phone costs the
    generator little."""
    at = body.find(_PROBE)
    if at < 0:
        return None
    start = at + len(_PROBE)
    return body[start : body.index(b'"', start)].decode()


async def phone(
    client: httpx.AsyncClient, stats: Stats, stop: float, poll_s: float, building: str
) -> None:
    etags: dict[str, str] = {}
    seen = Seen()
    stats.phones.append(seen.changes)
    await asyncio.sleep(random.uniform(0, poll_s))  # spread the herd
    while time.perf_counter() < stop:
        for path, name in (
            ("/api/buildings", "GET buildings"),
            (f"/api/buildings/{building}", "GET building"),
        ):
            headers = {"If-None-Match": etags[path]} if path in etags else {}
            r = await timed(stats, name, client.get(path, headers=headers))
            stats.requests += 1
            if r is not None and r.status_code == 200:
                etags[path] = r.headers.get("etag", "")
                stats.received += len(r.content)
                if name == "GET building" and (state := probe_state(r.content)):
                    seen.saw(state)
        await asyncio.sleep(poll_s)


async def sse_phone(client: httpx.AsyncClient, stats: Stats, stop: float, building: str) -> None:
    """One app with its stream open, reconnecting like the frontend if it drops."""
    seen = Seen()
    stats.phones.append(seen.changes)
    longest = 0.0
    await asyncio.sleep(random.uniform(0, RAMP_S))  # connect over RAMP_S, not in one burst
    while (left := stop - time.perf_counter()) > 0:
        opened = time.perf_counter()
        stats.requests += 1
        try:
            async with asyncio.timeout(left):
                async with client.stream("GET", f"/api/live?building={building}") as r:
                    stats.status["GET live"][r.status_code] += 1
                    last, event = None, b""
                    async for line in r.aiter_lines():
                        stats.received += len(line) + 1
                        if line.startswith("event: "):
                            event = line[7:].encode()
                        elif line.startswith("data: ") and event == b"building":
                            if state := probe_state(line[6:].encode()):
                                seen.saw(state)
                        elif line == "":
                            now = time.perf_counter()
                            if last is None:
                                stats.first_event.append(now - opened)
                            elif now - last > longest:
                                longest = now - last
                            last = now
        except TimeoutError:
            break  # the run is over
        except httpx.HTTPError as exc:
            stats.errors[f"GET live {type(exc).__name__}"] += 1
            await asyncio.sleep(random.uniform(0.5, 1.5))
    stats.longest_gap.append(longest)


async def probe(client: httpx.AsyncClient, stats: Stats, stop: float, key: str) -> None:
    """Flips the probe seat every PROBE_FLIP_S, posting every second like a node, and records
    T0 for each flip as it commits. It starts once every phone has connected."""
    await asyncio.sleep(RAMP_S + 2)
    occupied = False
    while time.perf_counter() < stop:
        occupied = not occupied
        flip_at = time.perf_counter() + PROBE_FLIP_S
        committed = False
        while time.perf_counter() < min(flip_at, stop):
            sent = time.monotonic()
            reading = {"seat_id": PROBE_SEAT, "object_present": occupied, "human_present": occupied}
            try:
                r = await client.post(
                    "/api/readings",
                    json={"node_id": PROBE_NODE, "readings": [reading]},
                    headers={"X-Node-Key": key},
                )
            except httpx.HTTPError:
                await asyncio.sleep(1)
                continue
            received = time.monotonic()
            led = r.json().get("leds", {}).get(PROBE_SEAT) if r.status_code == 200 else None
            if not committed and (led == PERSON_LED) == occupied and led in ("red", "green"):
                stats.flips.append((received, "occupied" if occupied else "open"))
                stats.probe_rtt.append(received - sent)
                committed = True
            await asyncio.sleep(1)


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


@dataclass(frozen=True)
class Part:
    """One generator process's share of the load."""

    base_url: str
    mode: str
    building: str
    clients: int
    nodes: range
    seconds: float
    poll_s: float
    with_probe: bool


async def run(part: Part) -> Stats:
    key = os.environ.get("NODE_KEY", "")
    stats = Stats()
    stop = time.perf_counter() + part.seconds
    size = part.clients + len(part.nodes) + 1
    limits = httpx.Limits(max_connections=size, max_keepalive_connections=size)
    # A stream waits up to 3 x POLL_WEB_S for its next event before it counts as broken.
    timeout = httpx.Timeout(10, read=3 * part.poll_s)
    async with httpx.AsyncClient(base_url=part.base_url, limits=limits, timeout=timeout) as client:
        if part.mode == "sse":
            tasks = [sse_phone(client, stats, stop, part.building) for _ in range(part.clients)]
        else:
            tasks = [
                phone(client, stats, stop, part.poll_s, part.building) for _ in range(part.clients)
            ]
        tasks += [node(client, stats, stop, n, key) for n in part.nodes]
        if part.with_probe:
            tasks.append(probe(client, stats, stop, key))
        await asyncio.gather(*tasks)
    return stats


def _run_part(part: Part) -> Stats:
    started = resource.getrusage(resource.RUSAGE_SELF)
    stats = asyncio.run(run(part))
    ended = resource.getrusage(resource.RUSAGE_SELF)
    stats.cpu_s = (ended.ru_utime - started.ru_utime) + (ended.ru_stime - started.ru_stime)
    return stats


def db_transactions() -> int | None:
    """Committed and rolled-back transactions so far in DATABASE_URL, or None if unreadable."""
    try:
        import psycopg

        from app.config import get_settings

        with psycopg.connect(get_settings().database_url) as conn:
            row = conn.execute(
                b"SELECT xact_commit + xact_rollback FROM pg_stat_database"
                b" WHERE datname = current_database()"
            ).fetchone()
        return int(row[0]) if row else None
    except Exception:
        return None


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
    parser.add_argument("--mode", choices=("poll", "sse"), default="poll")
    parser.add_argument(
        "--building", help="the building phones watch (default: loadtest with --setup, else pcl)"
    )
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
    building = args.building or (LOAD_BUILDING if args.setup else "pcl")
    if args.setup:
        setup(args.nodes)
    # One asyncio process saturates a core around 500 clients, which then measures the generator
    # rather than the backend; split the load across processes and merge the samples.
    jobs = [
        Part(
            base_url=args.base_url,
            mode=args.mode,
            building=building,
            clients=len(range(i, args.clients, args.procs)),
            nodes=range(i, args.nodes, args.procs),
            seconds=args.seconds,
            poll_s=args.poll,
            with_probe=args.setup and i == 0,
        )
        for i in range(args.procs)
    ]
    transactions = db_transactions()
    try:
        with multiprocessing.Pool(args.procs) as pool:
            parts = pool.map(_run_part, jobs)
    finally:
        after = db_transactions()
        if args.setup:
            teardown()
    stats = Stats()
    for part in parts:
        stats.merge(part)
    print(
        f"{args.mode}: {args.clients} clients on {building!r}, {args.nodes} nodes,"
        f" {args.procs} generator processes, {args.seconds:.0f} s against {args.base_url}"
    )
    print(stats.report())
    print(stats.report_live(args.seconds, args.procs))
    if transactions is not None and after is not None:
        print(f"database transactions: {(after - transactions) / args.seconds:.0f}/s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
