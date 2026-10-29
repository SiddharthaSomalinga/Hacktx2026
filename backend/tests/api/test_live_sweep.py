"""Per-user live hints in real flows (D61): the sweep, tick completeness, and an oracle walk."""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import Any

import pytest

from app.domain.types import Reading, UserChange
from app.services.ports import UserHint
from app.worker import Worker
from tests.api.conftest import World
from tests.api.harness import BAG, EMPTY, PERSON, Phone
from tests.api.test_social_flows import host_at, matched
from tests.world import NODE, REAL_SEATS, USERS


def hinted_since(world: World, mark: int) -> dict[str, set[UserChange]]:
    out: dict[str, set[UserChange]] = {}
    for batch in world.repo.feed.published[mark:]:
        for hint in batch:
            if isinstance(hint, UserHint):
                out.setdefault(hint.user_id, set()).update(hint.changes)
    return out


def sense_only(world: World, seats: dict[str, tuple[bool, bool]]) -> None:
    """A node post that leaves the other seats out, as if their sensors had died."""
    world.services.readings.ingest(NODE, [Reading(s, *v) for s, v in seats.items()])


def test_a_lapsing_presence_is_hinted_by_the_sweep(world: World) -> None:
    host_at(world, "alex", "s1")
    since = world.clock.now()
    world.clock.advance(11)  # past HUMAN_FRESH_S, nothing written: alex is now away
    mark = len(world.repo.feed.published)
    assert world.services.scheduler.sweep(since, world.clock.now()) == 1
    assert hinted_since(world, mark) == {"alex": {UserChange.TIME}}


def test_a_table_mate_going_offline_is_hinted_by_the_sweep(world: World) -> None:
    for seat in ("s2", "s3"):
        world.node.set(seat, PERSON)
    host_at(world, "alex", "s1")  # s4 is the table's only open seat
    assert world.phone("alex").ok("GET", "/api/me")["host"]["status"] == "findable"
    for _ in range(14):  # 28 s in which s4 never reports again
        world.clock.advance(2)
        sense_only(world, {"s1": PERSON, "s2": PERSON, "s3": PERSON})
    since = world.clock.now()
    world.clock.advance(3)  # s4 goes offline (OFFLINE_S) inside this window
    mark = len(world.repo.feed.published)
    world.services.scheduler.sweep(since, world.clock.now())
    assert hinted_since(world, mark) == {"alex": {UserChange.TIME}}
    assert world.phone("alex").ok("GET", "/api/me")["host"]["hidden_reason"] == "table_full"


def test_an_alternative_seat_moving_with_time_is_hinted_to_both(world: World) -> None:
    _, priya, mid = matched(world)
    world.node.set("s2", PERSON)  # the assigned seat is taken: the alternative is s3
    world.node.post()
    assert priya.ok("GET", f"/api/matches/{mid}")["alt_seat_id"] == "s3"
    for _ in range(14):  # s3 stops reporting
        world.clock.advance(2)
        sense_only(world, {"s1": PERSON, "s2": PERSON, "s4": EMPTY})
    since = world.clock.now()
    world.clock.advance(3)  # s3 goes offline inside this window
    mark = len(world.repo.feed.published)
    world.services.scheduler.sweep(since, world.clock.now())
    assert set(hinted_since(world, mark)) == {"alex", "priya"}
    assert priya.ok("GET", f"/api/matches/{mid}")["alt_seat_id"] == "s4"


def test_a_quiet_window_hints_nobody(world: World) -> None:
    host_at(world, "alex", "s1")
    since = world.clock.now()
    world.clock.advance(1)
    mark = len(world.repo.feed.published)
    assert world.services.scheduler.sweep(since, world.clock.now()) == 0
    assert world.repo.feed.published[mark:] == []


# --- every per-user change is hinted, with no client polling ------------------------------


def view_of(phone: Phone) -> dict[str, Any]:
    """Everything the user's screens can fetch, minus the countdowns (counted on the client)."""
    me = phone.ok("GET", "/api/me")
    out: dict[str, Any] = {"me": me}
    if me["search_id"]:
        search = phone.ok("GET", f"/api/search/{me['search_id']}")
        search.pop("seconds_left")
        out["search"] = search
    if me["host"]:
        out["inbox"] = [
            {k: v for k, v in item.items() if k != "seconds_left"}
            for item in phone.ok("GET", "/api/host/inbox")
        ]
    if me["match_id"]:
        out["match"] = phone.ok("GET", f"/api/matches/{me['match_id']}")
    return out


def actions(world: World, phones: dict[str, Phone], rng: random.Random) -> list[Callable[[], Any]]:
    seat = rng.choice(REAL_SEATS)
    user = rng.choice(USERS)
    phone = phones[user]

    def sense() -> None:
        world.node.set(seat, rng.choice([PERSON, BAG, EMPTY]))
        world.node.post()

    def wait() -> None:
        world.node.run(rng.choice([1, 3, 11, 31, 121, 301]))

    def silence() -> None:
        world.node.online = not world.node.online

    def host() -> None:
        phone.http.post("/api/host/link", json={"seat_id": seat})
        phone.http.post("/api/host/topic", json={"topic_raw": "orgo 1"})

    def stop_hosting() -> None:
        phone.http.post("/api/host/toggle", json={"open": False})

    def mute() -> None:
        phone.http.post("/api/host/mute", json={"muted": rng.random() < 0.5})

    def search() -> None:
        r = phone.http.post("/api/search", json={"topic_raw": "orgo 1 exam"})
        if r.status_code == 200:
            phone.http.post(f"/api/search/{r.json()['search_id']}/join")

    def answer() -> None:
        r = phone.http.get("/api/host/inbox")
        if r.status_code == 200 and r.json():
            rid = r.json()[0]["request_id"]
            phone.http.post(f"/api/requests/{rid}/{rng.choice(['accept', 'decline'])}")

    def end() -> None:
        me = phone.http.get("/api/me").json()
        if me["match_id"]:
            phone.http.post(f"/api/matches/{me['match_id']}/{rng.choice(['arrived', 'cancel'])}")
        elif me["search_id"]:
            phone.http.post(f"/api/search/{me['search_id']}/cancel")

    return [sense, sense, sense, wait, wait, silence, host, host, stop_hosting, mute, search,
            search, answer, answer, end]  # fmt: skip


@pytest.mark.parametrize("seed", range(10))
def test_every_change_a_user_can_see_was_hinted(world: World, seed: int) -> None:
    """The live stream's promise: with no polling, a user's screens still change only when
    they were told to refetch. Each step acts, lets the worker run, then compares every
    user's views with the previous step's. Reading the views must itself write nothing,
    which proves the tick covers every transition a poll used to trigger."""
    rng = random.Random(seed)
    phones = {u: world.phone(u) for u in USERS}
    worker = Worker(world.services, tick_s=2)
    previous = {u: view_of(p) for u, p in phones.items()}
    for step in range(150):
        mark = len(world.repo.feed.published)
        rng.choice(actions(world, phones, rng))()
        worker.run_once()
        hinted = hinted_since(world, mark)  # the action's writes, then the worker's
        reading = len(world.repo.feed.published)
        views = {u: view_of(p) for u, p in phones.items()}
        assert world.repo.feed.published[reading:] == [], f"step {step}: a GET wrote"
        for u in USERS:
            if views[u] != previous[u]:
                assert u in hinted, f"step {step}: {u}'s view changed without a hint"
        previous = views
