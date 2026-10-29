"""The in-app worker drives expiries and push with no client polling (D29, D30)."""

from __future__ import annotations

from dataclasses import replace

from app.domain.types import RequestStatus
from app.worker import Worker
from tests.api.conftest import World
from tests.api.harness import PERSON
from tests.conftest import make_settings


def test_worker_moves_an_expired_request_and_pushes_it(world: World) -> None:
    world.node.set("s1", PERSON)
    world.node.set("s2", PERSON)
    world.node.post()
    for user, seat in (("alex", "s1"), ("jordan", "s2")):
        p = world.phone(user)
        p.ok("POST", "/api/host/link", {"seat_id": seat})
        p.ok("POST", "/api/host/topic", {"topic_raw": "orgo 1"})
        p.ok(
            "POST",
            "/api/push/subscribe",
            {"endpoint": f"https://push/{user}", "keys": {"p256dh": "k", "auth": "a"}},
        )
    priya = world.phone("priya")
    sid = priya.ok("POST", "/api/search", {"topic_raw": "orgo 1"})["search_id"]
    priya.ok("POST", f"/api/search/{sid}/join")

    worker = Worker(world.services, tick_s=0.01)
    worker.run_once()
    assert len(world.notifier.sent) == 1  # the first host's request was pushed
    world.node.run(make_settings().request_timeout_s)  # times out; nobody opens the app
    worker.run_once()
    assert len(world.notifier.sent) == 2
    first, second = (endpoint for endpoint, _ in world.notifier.sent)
    assert first != second  # the next host was asked, and told


def test_worker_resumes_a_search_left_without_a_pending_request(world: World) -> None:
    """A failure between a request's expiry and the next send leaves the search joined, active
    and with nothing pending. Only the seeker's own status poll used to recover it."""
    world.node.set("s1", PERSON)
    world.node.set("s2", PERSON)
    world.node.post()
    for user, seat in (("alex", "s1"), ("jordan", "s2")):
        p = world.phone(user)
        p.ok("POST", "/api/host/link", {"seat_id": seat})
        p.ok("POST", "/api/host/topic", {"topic_raw": "orgo 1"})
    priya = world.phone("priya")
    sid = priya.ok("POST", "/api/search", {"topic_raw": "orgo 1"})["search_id"]
    priya.ok("POST", f"/api/search/{sid}/join")
    first = world.repo.data.requests.copy()
    (pending,) = first.values()
    world.repo.data.requests[pending.id] = replace(pending, status=RequestStatus.EXPIRED)

    worker = Worker(world.services, tick_s=0.01)
    worker.run_once()
    world.node.run(30)  # the hosts stay; nobody polls the search
    worker.run_once()
    pending_now = [
        r for r in world.repo.data.requests.values() if r.status is RequestStatus.PENDING
    ]
    assert len(pending_now) == 1 and pending_now[0].id not in first


def test_worker_thread_starts_and_stops(world: World) -> None:
    worker = Worker(world.services, tick_s=0.01)
    worker.start()
    worker.stop(timeout=2)
    assert not worker._thread.is_alive()


def test_a_failing_tick_does_not_stop_the_loop(world: World, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def boom() -> int:
        calls.append(1)
        raise RuntimeError("database down")

    monkeypatch.setattr(world.services.scheduler, "tick", boom)
    worker = Worker(world.services, tick_s=0.01)
    worker.run_once()
    worker.run_once()
    assert len(calls) == 2
