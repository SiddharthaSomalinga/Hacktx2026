"""GET /api/live over HTTP (D61): framing, the first events, identity, errors, cleanup."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.adapters.ai_fallback import FallbackAI
from app.domain.live import format_version, version_of
from app.main import create_app
from app.services.container import Services
from app.services.context import Context
from tests.conftest import make_settings
from tests.fakes import FakeClock, FakeNotifier, InMemoryRepository, RecordingMetrics
from tests.world import build_world


@dataclass
class Live:
    http: TestClient
    services: Services
    metrics: RecordingMetrics


@pytest.fixture
def live() -> Iterator[Live]:
    repo, metrics = InMemoryRepository(), RecordingMetrics()
    build_world(repo)
    settings = make_settings()
    ctx = Context(
        repo=repo,  # type: ignore[arg-type]
        ai=FallbackAI(),
        notifier=FakeNotifier(),
        clock=FakeClock(),
        timers=settings.timers(),
        map_cache_s=0,
        history_window_h=settings.history_window_h,
        push_max_attempts=settings.push_max_attempts,
        vapid_public_key=settings.vapid_public_key,
        metrics=metrics,
        live_ping_s=0.1,
    )
    services = Services.build(ctx)
    with TestClient(create_app(settings, services)) as http:
        yield Live(http, services, metrics)


def events(lines: Iterator[str]) -> Iterator[dict[str, str]]:
    """Parse an event stream: each event's fields, data lines joined."""
    event: dict[str, str] = {}
    for line in lines:
        if line == "":
            if event:
                yield event
            event = {}
            continue
        name, _, value = line.partition(": ")
        event[name] = event[name] + "\n" + value if name in event else value


def wait_until(condition, within: float = 2.0) -> None:  # type: ignore[no-untyped-def]
    deadline = time.monotonic() + within
    while not condition():
        assert time.monotonic() < deadline, "timed out"
        time.sleep(0.01)


def test_the_stream_opens_with_retry_then_both_snapshots_as_the_gets_serve_them(
    live: Live,
) -> None:
    buildings = live.http.get("/api/buildings")
    lib = live.http.get("/api/buildings/lib")
    with live.http.stream("GET", "/api/live?building=lib") as r:
        assert r.status_code == 200
        assert r.headers["content-type"].startswith("text/event-stream")
        assert r.headers["cache-control"] == "no-cache"
        assert "content-length" not in r.headers
        stream = events(r.iter_lines())
        retry = next(stream)
        assert 1000 <= int(retry["retry"]) <= 3000  # LIVE_RETRY_S 2 s, ±50%
        first, second = next(stream), next(stream)
    assert (first["event"], first["data"].encode()) == ("buildings", buildings.content)
    assert (second["event"], second["data"].encode()) == ("building", lib.content)
    assert second["id"] == format_version(
        version_of(buildings.headers["etag"]), version_of(lib.headers["etag"])
    )


def test_a_reconnect_that_has_everything_gets_a_ping_first(live: Live) -> None:
    have = format_version(
        version_of(live.http.get("/api/buildings").headers["etag"]),
        version_of(live.http.get("/api/buildings/lib").headers["etag"]),
    )
    headers = {"Last-Event-ID": have}
    with live.http.stream("GET", "/api/live?building=lib", headers=headers) as r:
        stream = events(r.iter_lines())
        next(stream)  # retry
        ping = next(stream)
    assert (ping["event"], json.loads(ping["data"])) == ("ping", {"db": True, "hints": True})
    assert ping["id"] == have


def test_errors_before_the_stream_are_the_usual_json(live: Live) -> None:
    r = live.http.get("/api/live?building=nope")
    assert (r.status_code, r.json()["error"]) == (404, "building_not_found")
    r = live.http.get("/api/live?building=" + "x" * 65)
    assert (r.status_code, r.json()["error"]) == (422, "validation_error")


def test_only_a_logged_in_stream_hears_about_its_user_and_only_topic_names(live: Live) -> None:
    live.http.post("/api/login", json={"user_id": "alex"})
    anonymous = TestClient(live.http.app)
    node = {
        "node_id": "n1",
        "readings": [{"seat_id": "s1", "object_present": True, "human_present": True}],
    }
    with (
        live.http.stream("GET", "/api/live") as mine,
        anonymous.stream("GET", "/api/live") as theirs,
    ):
        my_events, their_events = events(mine.iter_lines()), events(theirs.iter_lines())
        for stream in (my_events, their_events):
            next(stream), next(stream)  # retry, buildings
        live.http.post(
            "/api/readings", json=node, headers={"X-Node-Key": "test-node-key-0123456789"}
        )
        assert live.http.post("/api/host/link", json={"seat_id": "s1"}).status_code == 200
        seen = []
        while len(seen) < 6 and (event := next(my_events)).get("event") != "invalidate":
            seen.append(event)
        assert event["event"] == "invalidate"
        assert re.fullmatch(
            r'\["(inbox|match|me|search)"(,"(inbox|match|me|search)")*\]', event["data"]
        )
        assert "alex" not in event["data"] and "s1" not in event["data"]
        kinds = {next(their_events)["event"] for _ in range(4)}
    assert "invalidate" not in kinds


def test_leaving_closes_the_subscription_and_counts_as_a_stream(live: Live) -> None:
    hub = live.services.live.hub
    with live.http.stream("GET", "/api/live?building=lib") as r:
        stream = events(r.iter_lines())
        next(stream), next(stream), next(stream)
        assert hub.watched == 2
    wait_until(lambda: hub.watched == 0)
    wait_until(lambda: live.metrics.streams_closed != [])
    assert live.metrics.streams_open == 0
    assert all(route != "/api/live" for _, route, _ in live.metrics.requests)
    assert live.metrics.bytes["/api/live"] > 0


def test_when_live_is_off_clients_get_a_404_and_poll(live: Live) -> None:
    from dataclasses import replace

    off = make_settings(live_enabled=False)
    services = Services.build(replace(live.services.ctx, live_enabled=False))
    with TestClient(create_app(off, services)) as http:
        r = http.get("/api/live")
        assert http.get("/api/buildings").status_code == 200
    assert (r.status_code, r.json()["error"]) == (404, "live_disabled")
