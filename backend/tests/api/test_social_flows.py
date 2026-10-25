"""Both user flows end to end (USER_FLOWS v1.1; FR-14..54; D17..D25)."""

from __future__ import annotations

import uuid
from datetime import timedelta

from app.domain.types import HostSession
from app.services.ports import PushResult
from tests.api.conftest import World
from tests.api.harness import BAG, PERSON, Phone
from tests.conftest import make_settings
from tests.fakes import Subscription

ORGO = "dying on ch 320m stereochem mechanisms"

REQUEST_TIMEOUT_S = make_settings().request_timeout_s  # D42: 300


def host_at(world: World, user: str, seat: str, topic: str = ORGO) -> Phone:
    """Sit down, link the seat, enter a topic (host flow, D17)."""
    world.node.set(seat, PERSON)
    world.node.post()
    phone = world.phone(user)
    phone.ok("POST", "/api/host/link", {"seat_id": seat})
    phone.ok("POST", "/api/host/topic", {"topic_raw": topic})
    return phone


def seeker(
    world: World, user: str = "priya", topic: str = "orgo 1 exam prep"
) -> tuple[Phone, dict]:  # type: ignore[type-arg]
    phone = world.phone(user)
    return phone, phone.ok("POST", "/api/search", {"topic_raw": topic})


def add_sim_host(world: World, seat: str = "t2-s3", course: str = "CH 320M") -> None:
    world.repo.data.sessions["sim1"] = HostSession(
        "sim1",
        "simhost",
        seat,
        "orgo",
        course,
        "chemistry",
        ("orgo",),
        None,
        True,
        False,
        world.clock.now(),
        world.clock.now() + timedelta(days=365),
        None,
        None,
        None,
        f"{course}",
    )


# --- accounts ------------------------------------------------------------------


def test_demo_login_me_and_logout(world: World) -> None:
    anon = world.phone()
    assert anon.ok("GET", "/api/me") == {
        "user": None,
        "host": None,
        "search_id": None,
        "match_id": None,
    }
    assert {u["id"] for u in anon.ok("GET", "/api/demo-users")} == {
        "alex",
        "priya",
        "jordan",
        "sam",
    }
    assert anon.error("POST", "/api/login", {"user_id": "simhost"}) == (404, "unknown_user")
    assert anon.error("POST", "/api/search", {"topic_raw": "x"}) == (401, "not_logged_in")
    alex = world.phone("alex")
    assert alex.ok("GET", "/api/me")["user"] == {
        "id": "alex",
        "first_name": "Alex",
        "major": "Biochemistry",
    }
    alex.ok("POST", "/api/logout")
    assert alex.ok("GET", "/api/me")["user"] is None


# --- host flow -----------------------------------------------------------------


def test_cannot_link_an_empty_seat_or_a_bag(world: World) -> None:
    alex = world.phone("alex")
    world.node.post()
    assert alex.error("POST", "/api/host/link", {"seat_id": "s1"}) == (409, "seat_not_occupied")
    world.node.set("s1", BAG)
    world.node.post()
    assert alex.error("POST", "/api/host/link", {"seat_id": "s1"}) == (409, "seat_not_occupied")
    assert alex.error("POST", "/api/host/link", {"seat_id": "t2-s1"}) == (409, "seat_not_occupied")
    assert alex.error("POST", "/api/host/link", {"seat_id": "zzz"}) == (404, "seat_not_found")


def test_host_setup_order_and_findability(world: World) -> None:
    world.node.set("s1", PERSON)
    world.node.post()
    alex = world.phone("alex")
    assert alex.error("POST", "/api/host/topic", {"topic_raw": "x"}) == (409, "not_linked")
    sid = alex.ok("POST", "/api/host/link", {"seat_id": "s1"})["session_id"]
    assert alex.ok("POST", "/api/host/link", {"seat_id": "s1"})["session_id"] == sid  # idempotent
    host = alex.ok("GET", "/api/me")["host"]
    assert host["status"] == "hidden" and host["hidden_reason"] == "needs_topic"
    topic = alex.ok("POST", "/api/host/topic", {"topic_raw": ORGO})
    assert topic["course_code"] == "CH 320M"
    assert alex.ok("GET", "/api/me")["host"]["status"] == "findable"


def test_stepping_away_hides_then_ten_minutes_with_a_bag_ends_the_session(world: World) -> None:
    alex = host_at(world, "alex", "s1")
    world.node.set("s1", BAG)  # D18: belongings never count as presence
    world.node.run(12)
    assert alex.ok("GET", "/api/me")["host"]["hidden_reason"] == "away"
    world.node.set("s1", PERSON)
    world.node.run(2)
    assert alex.ok("GET", "/api/me")["host"]["status"] == "findable"
    world.node.set("s1", BAG)
    world.node.post()
    world.node.run(600)
    assert alex.ok("GET", "/api/me")["host"] is None
    assert world.repo.data.sessions[next(iter(world.repo.data.sessions))].end_reason == "no_person"


def test_full_table_hides_the_host(world: World) -> None:
    alex = host_at(world, "alex", "s1")
    for s in ("s2", "s3", "s4"):
        world.node.set(s, PERSON)
    world.node.post()
    assert alex.ok("GET", "/api/me")["host"]["hidden_reason"] == "table_full"


def test_toggle_off_ends_the_session(world: World) -> None:
    alex = host_at(world, "alex", "s1")
    assert alex.ok("POST", "/api/host/toggle", {"open": True}) == {"open": True}
    assert alex.ok("POST", "/api/host/toggle", {"open": False}) == {"open": False}
    assert alex.ok("GET", "/api/me")["host"] is None
    assert alex.error("POST", "/api/host/toggle", {"open": True}) == (409, "not_linked")


def test_three_hour_confirmation(make_world) -> None:  # type: ignore[no-untyped-def]
    w: World = make_world(map_cache_s=0, session_max_s=60, confirm_grace_s=120)
    alex = host_at(w, "alex", "s1")
    assert alex.error("POST", "/api/host/confirm") == (409, "confirm_not_due")
    w.node.run(60)
    assert alex.ok("GET", "/api/me")["host"]["hidden_reason"] == "confirm_pending"
    assert [m.message.kind for m in w.repo.data.outbox] == ["confirm_needed"]
    alex.ok("POST", "/api/host/confirm")
    assert alex.ok("GET", "/api/me")["host"]["status"] == "findable"
    w.node.run(60 + 120)
    assert alex.ok("GET", "/api/me")["host"] is None  # no answer within the grace window
    assert [m.message.kind for m in w.repo.data.outbox][-1] == "session_ended"


# --- seeker flow ---------------------------------------------------------------


def test_search_hides_names_but_join_shows_first_name_and_major(world: World) -> None:
    alex = host_at(world, "alex", "s1")
    priya, found = seeker(world)
    assert found["label"] == "CH 320M · Organic Chemistry I"
    assert found["offered_group"] == "same_course" and found["has_real_hosts"] is True
    assert found["same_course"] == [{"building_id": "lib", "floor": 1, "count": 1}]
    assert "Alex" not in str(found)
    status = priya.ok("POST", f"/api/search/{found['search_id']}/join")
    assert status["status"] == "active" and status["seconds_left"] == REQUEST_TIMEOUT_S
    # D43: before accept, each side sees the other's first name and major, nothing more.
    assert status["asking"] == {"first_name": "Alex", "major": "Biochemistry"}
    inbox = alex.ok("GET", "/api/host/inbox")
    assert (inbox[0]["seeker_first_name"], inbox[0]["seeker_major"]) == ("Priya", "Chemistry")
    assert inbox[0]["course_label"] == "CH 320M · Organic Chemistry I"
    assert inbox[0]["table_label"] == "Table 01"
    assert [m.message.kind for m in world.repo.data.outbox] == ["request_received"]


def test_related_group_is_offered_when_no_same_course_host(world: World) -> None:
    host_at(world, "alex", "s1", topic="gen chem 1 stoichiometry")
    _, found = seeker(world)
    assert found["offered_group"] == "related" and found["same_course"] == []
    assert found["related"] == [{"building_id": "lib", "floor": 1, "count": 1}]


def test_nobody_studying_this(world: World) -> None:
    _, found = seeker(world, topic="calc 2 series")
    assert found["same_course"] == [] and found["related"] == [] and not found["has_real_hosts"]


def test_simulated_hosts_count_but_join_is_refused_and_they_never_get_requests(
    world: World,
) -> None:
    add_sim_host(world)
    priya, found = seeker(world)
    assert found["same_course"] == [{"building_id": "lib", "floor": 1, "count": 1}]
    assert found["has_real_hosts"] is False
    assert priya.error("POST", f"/api/search/{found['search_id']}/join") == (409, "no_real_hosts")


def test_cascade_skips_simulated_and_declined_hosts_then_exhausts(world: World) -> None:
    add_sim_host(world)
    alex = host_at(world, "alex", "s1")
    jordan = host_at(world, "jordan", "s2")
    priya, found = seeker(world)
    sid = found["search_id"]
    priya.ok("POST", f"/api/search/{sid}/join")
    first = alex if alex.ok("GET", "/api/host/inbox") else jordan
    second = jordan if first is alex else alex
    rid = first.ok("GET", "/api/host/inbox")[0]["request_id"]
    first.ok("POST", f"/api/requests/{rid}/decline")
    assert first.ok("GET", "/api/host/inbox") == []
    assert len(second.ok("GET", "/api/host/inbox")) == 1
    rid = second.ok("GET", "/api/host/inbox")[0]["request_id"]
    second.ok("POST", f"/api/requests/{rid}/decline")
    assert priya.ok("GET", f"/api/search/{sid}")["status"] == "exhausted"
    assert world.repo.data.sessions["sim1"].id not in {
        r.host_session_id for r in world.repo.data.requests.values()
    }
    assert [m.message.kind for m in world.repo.data.outbox][-1] == "search_exhausted"


def test_request_expiry_moves_on_even_when_nobody_polls(world: World) -> None:
    alex = host_at(world, "alex", "s1")
    jordan = host_at(world, "jordan", "s2")
    priya, found = seeker(world)
    priya.ok("POST", f"/api/search/{found['search_id']}/join")
    world.node.run(REQUEST_TIMEOUT_S)  # nobody polls; only the node and the scheduler tick run
    world.services.scheduler.tick()
    pending = [r for r in world.repo.data.requests.values() if r.status == "pending"]
    assert len(pending) == 1 and len(world.repo.data.requests) == 2
    assert sum(len(p.ok("GET", "/api/host/inbox")) for p in (alex, jordan)) == 1


def test_absent_host_request_is_skipped(world: World) -> None:
    alex = host_at(world, "alex", "s1")
    priya, found = seeker(world)
    priya.ok("POST", f"/api/search/{found['search_id']}/join")
    world.node.set("s1", BAG)
    world.node.run(12)  # ingest notices the absence (FR-25)
    assert alex.ok("GET", "/api/host/inbox") == []
    assert priya.ok("GET", f"/api/search/{found['search_id']}")["status"] == "exhausted"


def test_mute_from_card_declines_and_can_be_undone(world: World) -> None:
    alex = host_at(world, "alex", "s1")
    priya, found = seeker(world)
    priya.ok("POST", f"/api/search/{found['search_id']}/join")
    rid = alex.ok("GET", "/api/host/inbox")[0]["request_id"]
    alex.ok("POST", f"/api/requests/{rid}/decline", {"mute": True})
    assert alex.ok("GET", "/api/me")["host"]["hidden_reason"] == "muted"
    alex.ok("POST", "/api/host/mute", {"muted": False})
    assert alex.ok("GET", "/api/me")["host"]["status"] == "findable"


def test_one_role_at_a_time(world: World) -> None:
    alex = host_at(world, "alex", "s1")
    assert alex.error("POST", "/api/search", {"topic_raw": "orgo"}) == (409, "already_hosting")
    priya, found = seeker(world)
    priya.ok("POST", f"/api/search/{found['search_id']}/join")
    world.node.set("s3", PERSON)
    world.node.post()
    assert priya.error("POST", "/api/host/link", {"seat_id": "s3"}) == (409, "already_searching")


def test_cancel_withdraws_the_pending_request(world: World) -> None:
    alex = host_at(world, "alex", "s1")
    priya, found = seeker(world)
    priya.ok("POST", f"/api/search/{found['search_id']}/join")
    assert priya.ok("POST", f"/api/search/{found['search_id']}/cancel") == {"status": "cancelled"}
    assert alex.ok("GET", "/api/host/inbox") == []


def test_rate_limit_per_hour(make_world) -> None:  # type: ignore[no-untyped-def]
    w: World = make_world(map_cache_s=0, max_requests_per_hour=1)
    host_at(w, "alex", "s1")
    priya, found = seeker(w)
    priya.ok("POST", f"/api/search/{found['search_id']}/join")
    priya.ok("POST", f"/api/search/{found['search_id']}/cancel")
    priya.ok("POST", "/api/search", {"topic_raw": "orgo 1"})
    sid = priya.ok("GET", "/api/me")["search_id"]
    assert priya.error("POST", f"/api/search/{sid}/join") == (429, "rate_limited")


def test_other_people_cannot_touch_a_search_or_request(world: World) -> None:
    alex = host_at(world, "alex", "s1")
    priya, found = seeker(world)
    sam = world.phone("sam")
    assert sam.error("GET", f"/api/search/{found['search_id']}") == (403, "not_your_search")
    priya.ok("POST", f"/api/search/{found['search_id']}/join")
    rid = alex.ok("GET", "/api/host/inbox")[0]["request_id"]
    assert sam.error("POST", f"/api/requests/{rid}/accept") == (403, "not_your_request")
    assert sam.error("GET", f"/api/search/{uuid.uuid4()}") == (404, "search_not_found")


# --- match ---------------------------------------------------------------------


def matched(world: World) -> tuple[Phone, Phone, str]:
    alex = host_at(world, "alex", "s1")
    priya, found = seeker(world)
    priya.ok("POST", f"/api/search/{found['search_id']}/join")
    rid = alex.ok("GET", "/api/host/inbox")[0]["request_id"]
    match_id = alex.ok("POST", f"/api/requests/{rid}/accept")["match_id"]
    return alex, priya, match_id


def test_accept_creates_the_match_blinks_blue_and_names_appear(world: World) -> None:
    alex, priya, mid = matched(world)
    assert world.node.post()["s1"] == "blue_blink"
    seen_by_seeker = priya.ok("GET", f"/api/matches/{mid}")
    assert seen_by_seeker["role"] == "seeker" and seen_by_seeker["other_first_name"] == "Alex"
    assert seen_by_seeker["assigned_seat_id"] == "s2"  # open seat next to the host (FR-37)
    assert seen_by_seeker["table_label"] == "Table 01" and seen_by_seeker["building"] == "Library"
    assert seen_by_seeker["card_url"] == "/cards/chemistry.png"
    assert "CH 320M" in seen_by_seeker["icebreaker"]
    assert alex.ok("GET", f"/api/matches/{mid}")["other_first_name"] == "Priya"
    search = priya.ok("GET", "/api/me")
    assert search["match_id"] == mid
    assert alex.ok("GET", "/api/me")["host"]["hidden_reason"] == "in_match"
    world.node.run(60)
    assert world.node.leds["s1"] == "red"  # blink lasts BLINK_S


def test_assigned_seat_taken_shows_alt_seat_to_both(world: World) -> None:
    alex, priya, mid = matched(world)
    world.node.set("s2", PERSON)
    world.node.post()
    assert priya.ok("GET", f"/api/matches/{mid}")["alt_seat_id"] == "s3"
    assert alex.ok("GET", f"/api/matches/{mid}")["alt_seat_id"] == "s3"


def test_arrival_completes_and_blinks_again(world: World) -> None:
    alex, priya, mid = matched(world)
    world.node.run(60)
    assert alex.error("POST", f"/api/matches/{mid}/arrived") == (403, "not_in_match")
    assert priya.ok("POST", f"/api/matches/{mid}/arrived") == {"status": "completed"}
    assert world.node.post()["s1"] == "blue_blink"
    assert alex.ok("GET", "/api/me")["host"]["status"] == "findable"  # findable again


def test_host_gone_two_minutes_cancels_and_notifies_both(world: World) -> None:
    _, priya, mid = matched(world)
    world.node.set("s1", BAG)
    world.node.post()
    world.node.run(120)
    assert priya.ok("GET", f"/api/matches/{mid}")["status"] == "cancelled"
    kinds = [m.message.kind for m in world.repo.data.outbox]
    assert kinds.count("match_cancelled") == 2


def test_match_expires_after_twenty_minutes(world: World) -> None:
    _, priya, mid = matched(world)
    world.node.run(1200)
    assert priya.ok("GET", f"/api/matches/{mid}")["status"] == "expired"


def test_either_side_cancels(world: World) -> None:
    _, priya, mid = matched(world)
    assert priya.ok("POST", f"/api/matches/{mid}/cancel") == {"status": "cancelled"}
    assert world.repo.data.outbox[-1].message.user_id == "alex"


def test_table_filled_before_accept_assigns_nearest_floor_seat(world: World) -> None:
    alex = host_at(world, "alex", "s1")
    priya, found = seeker(world)
    priya.ok("POST", f"/api/search/{found['search_id']}/join")
    for s in ("s2", "s3", "s4"):
        world.node.set(s, PERSON)
    world.node.post()
    rid = alex.ok("GET", "/api/host/inbox")[0]["request_id"]  # Q13: still pending
    mid = alex.ok("POST", f"/api/requests/{rid}/accept")["match_id"]
    assert priya.ok("GET", f"/api/matches/{mid}")["assigned_seat_id"].startswith("t2-")


# --- safety ----------------------------------------------------------------------


def test_blocks_apply_both_ways_and_report_also_blocks(world: World) -> None:
    alex = host_at(world, "alex", "s1")
    priya = world.phone("priya")
    alex.ok("POST", "/api/block", {"user_id": "priya"})
    _, found = seeker(world)
    assert found["same_course"] == []
    sam = world.phone("sam")
    sam.ok("POST", "/api/report", {"user_id": "alex", "reason": "rude"})
    found = sam.ok("POST", "/api/search", {"topic_raw": "orgo 1"})
    assert found["same_course"] == []
    assert priya.error("POST", "/api/block", {"user_id": "priya"}) == (422, "validation_error")
    assert priya.error("POST", "/api/block", {"user_id": "ghost"}) == (404, "unknown_user")


# --- push ------------------------------------------------------------------------


def test_push_delivery_retry_and_gone_subscriptions(world: World) -> None:
    alex = host_at(world, "alex", "s1")
    alex.ok(
        "POST",
        "/api/push/subscribe",
        {"endpoint": "https://push/a", "keys": {"p256dh": "k", "auth": "a"}},
    )
    priya, found = seeker(world)
    priya.ok("POST", f"/api/search/{found['search_id']}/join")
    assert world.services.push.drain() == 1
    endpoint, payload = world.notifier.sent[0]
    assert endpoint == "https://push/a" and payload["title"] == "New study request"
    # FR-53 / D43: first name and major before accept; no location beyond the host's table.
    assert payload["body"] == (
        "Priya · Chemistry wants to study CH 320M · Organic Chemistry I with you at Table 01."
    )

    world.notifier.results["https://push/a"] = PushResult.FAILED
    world.repo.data.outbox[0].sent_at = None
    assert world.services.push.drain() == 0  # retried later
    assert world.repo.data.outbox[0].attempts == 2
    world.notifier.results["https://push/a"] = PushResult.GONE
    assert world.services.push.drain() == 1
    assert world.repo.data.subscriptions == {}


def test_push_subscribe_validation(world: World) -> None:
    alex = world.phone("alex")
    bad = {"endpoint": "http://insecure", "keys": {"p256dh": "k", "auth": "a"}}
    assert alex.error("POST", "/api/push/subscribe", bad) == (422, "validation_error")
    assert world.phone().ok("GET", "/api/push/vapid-public-key") == {"key": "test-public-key"}
    world.repo.data.subscriptions["https://x"] = Subscription("priya", "https://x", "k", "a")
    alex.ok("DELETE", "/api/push/subscribe", {"endpoint": "https://x"})
    assert "https://x" in world.repo.data.subscriptions  # can't remove someone else's


def test_cascade_never_crosses_from_same_course_into_related(world: World) -> None:
    alex = host_at(world, "alex", "s1")  # CH 320M: same course
    jordan = host_at(world, "jordan", "s2", topic="gen chem 1")  # CH 301: related only
    priya, found = seeker(world)
    assert found["offered_group"] == "same_course"
    priya.ok("POST", f"/api/search/{found['search_id']}/join")
    rid = alex.ok("GET", "/api/host/inbox")[0]["request_id"]
    alex.ok("POST", f"/api/requests/{rid}/decline")
    assert priya.ok("GET", f"/api/search/{found['search_id']}")["status"] == "exhausted"
    assert jordan.ok("GET", "/api/host/inbox") == []  # D19: the seeker never agreed to related


def test_pinned_related_search_reaches_related_hosts(world: World) -> None:
    jordan = host_at(world, "jordan", "s2", topic="gen chem 1")
    host_at(world, "alex", "s1")
    priya = world.phone("priya")
    found = priya.ok("POST", "/api/search", {"topic_raw": "orgo 1", "group": "related"})
    assert found["offered_group"] == "related"  # FR-54: explicit opt-in
    priya.ok("POST", f"/api/search/{found['search_id']}/join")
    assert len(jordan.ok("GET", "/api/host/inbox")) == 1
