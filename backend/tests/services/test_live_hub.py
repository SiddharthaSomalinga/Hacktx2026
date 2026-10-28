"""The live hub (D61) against the in-memory repository: what streams receive, and when."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from typing import Any

import anyio
import anyio.to_thread
import pytest

from app.adapters.ai_fallback import FallbackAI
from app.domain.live import format_version, version_of
from app.domain.types import Reading
from app.services.container import Services
from app.services.context import Context
from app.services.errors import DomainError
from app.services.live import LiveEvent, LiveHub, Subscription
from app.services.map import to_cached
from app.services.ports import Resync, Unavailable
from tests.conftest import make_settings
from tests.fakes import FakeClock, FakeNotifier, InMemoryRepository
from tests.world import NODE, build_world

pytestmark = pytest.mark.anyio

PING_S = 0.2
PERSON = (True, True)
BAG = (True, False)


@pytest.fixture
async def world() -> AsyncIterator[tuple[Services, FakeClock]]:
    repo, clock = InMemoryRepository(), FakeClock()
    build_world(repo)
    settings = make_settings(map_cache_s=1, ghost_s=10)  # ghosted well before offline (30 s)
    ctx = Context(
        repo=repo,  # type: ignore[arg-type]
        ai=FallbackAI(),
        notifier=FakeNotifier(),
        clock=clock,
        timers=settings.timers(),
        map_cache_s=settings.map_cache_s,
        history_window_h=settings.history_window_h,
        push_max_attempts=settings.push_max_attempts,
        vapid_public_key=settings.vapid_public_key,
        # Background passes act only when the fake clock moves, so tests stay deterministic.
        live_check_s=1,
        live_ping_s=PING_S,
    )
    services = Services.build(ctx)
    async with anyio.create_task_group() as tg:
        tg.start_soon(services.live.hub.run)
        await wait_for(lambda: services.live.hub.hints_ok)
        yield services, clock
        tg.cancel_scope.cancel()


async def wait_for(condition: Callable[[], bool], within: float = 2.0) -> None:
    with anyio.fail_after(within):
        while not condition():
            await anyio.sleep(0.01)


async def next_event(events: AsyncIterator[LiveEvent], within: float = 2.0) -> LiveEvent:
    with anyio.fail_after(within):
        return await anext(events)


async def sense(services: Services, clock: FakeClock, seat: str, sensed: tuple[bool, bool]) -> None:
    """A node post, from a worker thread like a real request."""
    reading = Reading(seat, *sensed)
    await anyio.to_thread.run_sync(services.readings.ingest, NODE, [reading])


async def next_of(events: AsyncIterator[LiveEvent], kind: str) -> LiveEvent:
    """The next event of `kind`; after a change a stream gets `buildings`, then `building`."""
    while (event := await next_event(events)).kind != kind:
        assert event.kind != "ping", f"no {kind} event before the next ping"
    return event


def seat_state(event: LiveEvent, seat: str) -> str:
    detail: dict[str, Any] = json.loads(event.data)
    for floor in detail["floors"]:
        for table in floor["tables"]:
            for s in table["seats"]:
                if s["id"] == seat:
                    return str(s["state"])
    raise AssertionError(f"{seat} not in the snapshot")


async def open_lib(services: Services, user: str | None = None) -> tuple[Subscription, Any]:
    sub = await services.live.open(user, "lib", None)
    return sub, sub.events()


async def test_a_new_stream_gets_both_snapshots_exactly_as_the_gets_serve_them(
    world: tuple[Services, FakeClock],
) -> None:
    services, _ = world
    _, events = await open_lib(services)
    first, second = await next_event(events), await next_event(events)
    buildings, lib = services.map.buildings(), services.map.building("lib")
    assert (first.kind, first.data.encode()) == ("buildings", buildings.content)
    assert (second.kind, second.data.encode()) == ("building", lib.content)
    assert second.id == format_version(version_of(buildings.etag), version_of(lib.etag))


async def test_a_reconnect_with_current_versions_gets_only_a_ping(
    world: tuple[Services, FakeClock],
) -> None:
    services, _ = world
    have = format_version(
        version_of(services.map.buildings().etag), version_of(services.map.building("lib").etag)
    )
    sub = await services.live.open(None, "lib", have)
    event = await next_event(sub.events())
    assert (event.kind, json.loads(event.data)) == ("ping", {"db": True, "hints": True})


async def test_a_reading_that_changes_a_seat_is_pushed_at_once(
    world: tuple[Services, FakeClock],
) -> None:
    services, clock = world
    _, events = await open_lib(services)
    await next_event(events), await next_event(events)
    await sense(services, clock, "s1", PERSON)  # debounce is 0 in tests: occupied at once
    # The clock hasn't moved, so no periodic pass ran: the hint did this.
    assert (await next_event(events, within=1)).kind == "buildings"  # the counts changed
    assert seat_state(await next_of(events, "building"), "s1") == "occupied"


async def test_nothing_changed_means_a_ping_every_ping_interval(
    world: tuple[Services, FakeClock],
) -> None:
    services, clock = world
    _, events = await open_lib(services)
    await next_event(events), await next_event(events)
    clock.advance(5)
    await services.live.hub.run_once()  # a periodic pass that finds no change
    started = anyio.current_time()
    assert (await next_event(events)).kind == "ping"
    assert anyio.current_time() - started >= PING_S * 0.9


async def test_time_alone_turns_a_bag_into_likely_opening_with_no_write(
    world: tuple[Services, FakeClock],
) -> None:
    services, clock = world
    await sense(services, clock, "s2", BAG)
    _, events = await open_lib(services)
    first = [await next_event(events), await next_event(events)]
    assert seat_state(first[1], "s2") == "occupied"  # away, inside GHOST_S
    clock.advance(11)  # past GHOST_S, inside OFFLINE_S; nothing is written
    await services.live.hub.run_once()
    assert seat_state(await next_of(events, "building"), "s2") == "likely_opening"


async def test_a_slow_stream_skips_to_the_latest_state(world: tuple[Services, FakeClock]) -> None:
    services, _ = world
    sub, events = await open_lib(services)
    await next_event(events), await next_event(events)
    older, newer = to_cached({"v": 1}), to_cached({"v": 2})
    sub.offer("lib", older)
    sub.offer("lib", newer)  # before the stream read anything: it replaces the first
    event = await next_event(events)
    assert (event.kind, event.data) == ("building", '{"v":2}')
    assert (await next_event(events)).kind == "ping"


async def test_churn_is_broadcast_at_most_once_per_check_interval(
    world: tuple[Services, FakeClock],
) -> None:
    services, clock = world
    hub = services.live.hub
    _, events = await open_lib(services)
    await next_event(events), await next_event(events)
    await sense(services, clock, "s4", PERSON)  # a first change goes out at once
    await next_of(events, "building")
    builds = 0
    real = hub._build

    def counting(key: str):  # type: ignore[no-untyped-def]
        nonlocal builds
        builds += 1
        return real(key)

    hub._build = counting  # type: ignore[method-assign]
    await sense(services, clock, "s4", (False, False))  # a second, in the same instant
    await anyio.sleep(0.2)  # the hint has arrived; the rebuild waits for the gap
    await hub.run_once()
    assert builds == 0
    clock.advance(1)
    await hub.run_once()
    assert builds == 2  # the list and the building, on the periodic pass
    assert seat_state(await next_of(events, "building"), "s4") == "open"


async def test_a_database_outage_turns_pings_unhealthy(
    world: tuple[Services, FakeClock], monkeypatch: pytest.MonkeyPatch
) -> None:
    services, clock = world
    _, events = await open_lib(services)
    await next_event(events), await next_event(events)

    def down(*_: object, **__: object) -> object:
        raise Unavailable

    monkeypatch.setattr(services.map, "building", down)
    clock.advance(5)
    await services.live.hub.run_once()
    event = await next_event(events)
    assert (event.kind, json.loads(event.data)["db"]) == ("ping", False)


async def test_user_hints_reach_only_that_users_streams(
    world: tuple[Services, FakeClock],
) -> None:
    services, clock = world
    alex_sub, alex = await open_lib(services, "alex")
    _, priya = await open_lib(services, "priya")
    for events in (alex, priya):
        await next_event(events), await next_event(events)
    await sense(services, clock, "s1", PERSON)
    await anyio.to_thread.run_sync(services.host.link, "alex", "s1")
    seen = []
    while (event := await next_event(alex)).kind != "ping":
        seen.append(event)
    invalidations = [json.loads(e.data) for e in seen if e.kind == "invalidate"]
    assert invalidations and all(set(i) <= {"me", "inbox", "match"} for i in invalidations)
    while (event := await next_event(priya)).kind != "ping":
        assert event.kind != "invalidate"
    assert alex_sub.user_id == "alex"


async def test_a_reconnected_feed_tells_logged_in_streams_to_refetch_everything(
    world: tuple[Services, FakeClock],
) -> None:
    services, _ = world
    _, alex = await open_lib(services, "alex")
    _, anon = await open_lib(services)
    for events in (alex, anon):
        await next_event(events), await next_event(events)
    services.live.hub.on_hint(Resync())
    event = await next_event(alex)
    assert (event.kind, json.loads(event.data)) == (
        "invalidate",
        ["inbox", "match", "me", "search"],
    )
    assert (await next_event(anon)).kind == "ping"


async def test_closing_a_stream_stops_watching_its_snapshots(
    world: tuple[Services, FakeClock],
) -> None:
    services, _ = world
    hub: LiveHub = services.live.hub
    a, _ = await open_lib(services)
    b = await services.live.open(None, None, None)
    assert hub.watched == 2
    services.live.close(a)
    assert hub.watched == 1  # the buildings list, still watched by b
    services.live.close(b)
    assert hub.watched == 0


async def test_an_unknown_building_is_refused_before_streaming(
    world: tuple[Services, FakeClock],
) -> None:
    services, _ = world
    with pytest.raises(DomainError) as refused:
        await services.live.open(None, "nope", None)
    assert refused.value.code == "building_not_found"
    assert services.live.hub.watched == 0


async def test_live_disabled_is_a_404(world: tuple[Services, FakeClock]) -> None:
    services, _ = world
    off = replace(
        services,
        live=type(services.live)(replace(services.ctx, live_enabled=False), services.live.hub),
    )
    with pytest.raises(DomainError) as refused:
        await off.live.open(None, None, None)
    assert refused.value.code == "live_disabled"
