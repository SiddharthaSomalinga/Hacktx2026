"""Sensing, LEDs, map, recommendations, history (FR-1..13, FR-49, D21, D31, D32)."""

from __future__ import annotations

from collections.abc import Callable

from tests.api.conftest import World
from tests.api.harness import BAG, EMPTY, PERSON
from tests.conftest import NODE_KEY


def seat_states(w: World) -> dict[str, str]:
    detail = w.phone().ok("GET", "/api/buildings/lib")
    return {s["id"]: s["state"] for f in detail["floors"] for t in f["tables"] for s in t["seats"]}


def test_backpack_left_behind_turns_yellow_after_ghost_s(world: World) -> None:
    world.node.set("s1", PERSON)
    assert world.node.post()["s1"] == "red"
    world.node.set("s1", BAG)  # the person walks away, the bag stays
    world.node.post()  # sensed at t=0
    world.node.run(28)
    assert world.node.leds["s1"] == "red" and seat_states(world)["s1"] == "occupied"
    world.node.run(2)
    assert world.node.leds["s1"] == "yellow"
    assert seat_states(world)["s1"] == "likely_opening"


def test_map_never_exposes_away_or_durations(world: World) -> None:
    world.node.set("s1", BAG)
    world.node.run(60)
    body = world.phone().get("/api/buildings/lib").text
    assert "away" not in body and "since" not in body


def test_silent_node_goes_offline_and_leds_off(world: World) -> None:
    world.node.post()
    world.node.online = False
    world.node.run(30)
    assert seat_states(world)["s1"] == "offline"
    summary = {b["id"]: b for b in world.phone().ok("GET", "/api/buildings")}
    assert summary["lib"]["offline"] == 4


def test_change_only_storage_and_offline_marker(world: World) -> None:
    world.node.set("s1", BAG)
    world.node.run(20)  # 10 identical posts
    s1 = [r for r in world.repo.data.readings if r.seat_id == "s1"]
    assert len(s1) == 1
    world.node.online = False
    world.node.run(60)
    world.node.online = True
    world.node.post()
    s1 = [r for r in world.repo.data.readings if r.seat_id == "s1"]
    assert [r.online for r in s1] == [True, False, True]


def test_foreign_and_unknown_seats_are_skipped(world: World) -> None:
    r = world.node.http.post(
        "/api/readings",
        json={
            "node_id": "other-node",
            "readings": [{"seat_id": "s1", "object_present": True, "human_present": True}],
        },
        headers={"X-Node-Key": NODE_KEY},
    )
    assert r.json() == {"leds": {}}
    r = world.node.http.post(
        "/api/readings",
        json={
            "node_id": "n1",
            "readings": [{"seat_id": "nope", "object_present": True, "human_present": True}],
        },
        headers={"X-Node-Key": NODE_KEY},
    )
    assert r.json() == {"leds": {}}


def test_building_summary_and_detail_shape(world: World) -> None:
    world.node.set("s1", PERSON)
    world.node.post()
    lib = next(b for b in world.phone().ok("GET", "/api/buildings") if b["id"] == "lib")
    assert lib["total"] == 10 and lib["occupied"] == 1 and lib["open"] == 9
    detail = world.phone().ok("GET", "/api/buildings/lib")
    t1 = detail["floors"][0]["tables"][0]
    assert set(t1) == {"id", "label", "x", "y", "seats"}
    assert [s["position"] for s in t1["seats"]] == [1, 2, 3, 4]
    assert world.phone().error("GET", "/api/buildings/nope") == (404, "building_not_found")


def test_etag_round_trip_and_snapshot_cache(make_world: Callable[..., World]) -> None:
    w = make_world(map_cache_s=1)
    w.node.post()
    phone = w.phone()
    first = phone.get("/api/buildings/lib")
    etag = first.headers["etag"]
    assert phone.get("/api/buildings/lib", headers={"If-None-Match": etag}).status_code == 304
    w.node.set("s1", PERSON)
    w.node.post()  # monotonic clock unchanged: still inside MAP_CACHE_S
    assert phone.get("/api/buildings/lib").headers["etag"] == etag
    w.clock.advance(1)
    w.node.post()
    changed = phone.get("/api/buildings/lib", headers={"If-None-Match": etag})
    assert changed.status_code == 200 and changed.headers["etag"] != etag


def test_recommend_widens_and_reports_the_level(world: World) -> None:
    for s in ("s1", "s2", "s3", "s4"):
        world.node.set(s, PERSON)
    world.node.post()
    phone = world.phone()
    at_floor = phone.ok("GET", "/api/recommend?building_id=lib&table_id=t1")
    assert at_floor["level"] == "floor" and at_floor["table_id"] == "t2"  # busyness 0: t2 open
    world.node.set("s3", EMPTY)
    world.node.post()
    at_table = phone.ok("GET", "/api/recommend?building_id=lib&table_id=t1")
    assert at_table == {
        "seat_id": "s3",
        "table_id": "t1",
        "floor": 1,
        "kind": "open",
        "level": "table",
    }
    assert phone.error("GET", "/api/recommend?building_id=lib&table_id=x1") == (
        404,
        "table_not_found",
    )


def test_full_building_points_to_the_nearest_open_building(
    make_world: Callable[..., World],
) -> None:
    w = make_world(map_cache_s=0)
    for sid in [s for s in w.repo.data.seats if s.startswith("t2-")]:
        del w.repo.data.seats[sid]  # the library is now only the four real seats
    for s in ("s1", "s2", "s3", "s4"):
        w.node.set(s, PERSON)
    w.node.post()
    result = w.phone().ok("GET", "/api/recommend?building_id=lib")
    assert result == {"full": True, "nearest_building_id": "sim"}


def test_history_counts_open_time_from_change_only_rows(world: World) -> None:
    world.clock.advance(3600 - world.clock.now().minute * 60)  # start of an hour
    world.node.post()  # all four empty → open
    world.node.set("s1", PERSON)
    world.node.set("s2", PERSON)
    world.node.run(1800)  # half an hour with two of four real seats taken
    points = world.phone().ok("GET", "/api/buildings/lib/history")
    assert len(points) == 24
    last = points[-1]
    # Real seats only have readings; 2 seats open the whole 30 min, 2 open for ~0 s.
    assert 1.95 <= last["open_avg"] <= 2.05
