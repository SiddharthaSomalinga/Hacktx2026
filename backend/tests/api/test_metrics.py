"""GET /metrics and what the app records into it (D60)."""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.adapters.ai_fallback import FallbackAI
from app.adapters.metrics_prometheus import PrometheusMetrics
from app.domain.types import OutboxKind, OutboxMessage
from app.main import create_app
from app.services.container import Services
from app.services.context import Context
from app.services.ports import Metrics, PushOutcome, PushResult
from tests.conftest import make_settings
from tests.fakes import FakeClock, FakeNotifier, InMemoryRepository, RecordingMetrics
from tests.world import build_world

TOKEN = "metrics-token-for-tests"
BACKEND = Path(__file__).resolve().parents[2]

Build = Callable[..., tuple[TestClient, Services, InMemoryRepository]]


@pytest.fixture
def build(clock: FakeClock, notifier: FakeNotifier) -> Build:
    def make(
        metrics: Metrics, **overrides: object
    ) -> tuple[TestClient, Services, InMemoryRepository]:
        repo = InMemoryRepository()
        build_world(repo)
        settings = make_settings(map_cache_s=0, **overrides)
        ctx = Context(
            repo=repo,  # type: ignore[arg-type]
            ai=FallbackAI(),
            notifier=notifier,
            clock=clock,
            timers=settings.timers(),
            map_cache_s=0,
            history_window_h=settings.history_window_h,
            push_max_attempts=2,
            vapid_public_key=settings.vapid_public_key,
            demo_accept=timedelta(seconds=settings.demo_accept_s),
            metrics=metrics,
        )
        services = Services.build(ctx)
        return TestClient(create_app(settings, services)), services, repo

    return make


def _enqueue(repo: InMemoryRepository, clock: FakeClock, n: int) -> None:
    with repo.tx() as tx:
        tx.upsert_subscription("alex", "https://push.example/alex", "k", "a", clock.now())
        messages = [OutboxMessage("alex", OutboxKind.REQUEST_RECEIVED) for _ in range(n)]
        tx.enqueue(messages, clock.now())


def test_metrics_is_a_404_when_no_token_is_configured(build: Build) -> None:
    client, _, _ = build(PrometheusMetrics(None))
    r = client.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 404 and r.json()["error"] == "not_found"


@pytest.mark.parametrize(
    "authorization", [None, f"Bearer {TOKEN}x", f"Basic {TOKEN}", TOKEN, "Bearer "]
)
def test_metrics_refuses_anything_but_the_bearer_token(
    build: Build, authorization: str | None
) -> None:
    client, _, _ = build(PrometheusMetrics(None), metrics_token=TOKEN)
    headers = {"Authorization": authorization} if authorization is not None else {}
    r = client.get("/metrics", headers=headers)
    assert r.status_code == 401 and r.json()["error"] == "invalid_metrics_token"


def test_metrics_reports_requests_by_route_template_and_the_live_backlog(
    build: Build, clock: FakeClock
) -> None:
    client, _, repo = build(PrometheusMetrics(None), metrics_token=TOKEN)
    client.get("/api/buildings/lib")
    client.get("/api/buildings/lib")
    client.get("/wp-login.php/../../etc")  # a scanner: must not mint a new label
    _enqueue(repo, clock, 3)
    r = client.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/plain")
    body = r.text
    assert (
        'ghostseats_http_request_duration_seconds_count{method="GET",'
        'route="/api/buildings/{building_id}",status="200"} 2.0'
    ) in body
    assert 'route="unmatched"' in body and "wp-login" not in body
    assert "ghostseats_outbox_unsent 3.0" in body


def test_requests_ticks_and_push_outcomes_reach_the_port(
    build: Build, clock: FakeClock, notifier: FakeNotifier
) -> None:
    metrics = RecordingMetrics()
    client, services, repo = build(metrics)
    client.get("/api/buildings/lib")
    client.get("/api/nope")
    assert metrics.requests == [
        ("GET", "/api/buildings/{building_id}", 200),
        ("GET", "unmatched", 404),
    ]
    services.scheduler.tick()
    assert metrics.ticks == [0]

    _enqueue(repo, clock, 1)
    notifier.results["https://push.example/alex"] = PushResult.FAILED
    services.push.drain()  # attempt 1 of 2: kept for later
    services.push.drain()  # attempt 2 of 2: given up
    notifier.results.clear()
    _enqueue(repo, clock, 1)
    services.push.drain()
    assert metrics.pushes == [PushOutcome.RETRY, PushOutcome.GAVE_UP, PushOutcome.SENT]


def test_one_scrape_sums_every_worker_process(tmp_path: Path) -> None:
    """uvicorn --workers N: a scrape lands on one process but must report all of them."""
    record = (
        "from app.adapters.metrics_prometheus import PrometheusMetrics\n"
        f"m = PrometheusMetrics({str(tmp_path)!r})\n"
        "for _ in range(3):\n"
        "    m.observe_request('GET', '/api/health', 200, 0.01)\n"
    )
    env = {**os.environ, "PROMETHEUS_MULTIPROC_DIR": str(tmp_path)}
    for _ in range(2):
        subprocess.run([sys.executable, "-c", record], cwd=BACKEND, env=env, check=True)
    body, _ = PrometheusMetrics(str(tmp_path)).render(0)
    assert (
        b'ghostseats_http_request_duration_seconds_count{method="GET",'
        b'route="/api/health",status="200"} 6.0'
    ) in body
