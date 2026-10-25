"""Simulation (FR-47), recommendation widening (FR-11, D21), grouping (FR-29, D19), topics."""

from __future__ import annotations

import pytest

from app.domain.matching import aggregate, group_of, offered_group, rank
from app.domain.recommend import Full, Pick, Selection, recommend
from app.domain.simulation import simulated_state
from app.domain.topic_rules import (
    card_key_for,
    icebreaker_fallback,
    keyword_overlap,
    normalize_fallback,
)
from app.domain.types import Group, PublicState, RecommendLevel, SeatView
from tests.conftest import make_settings
from tests.domain.builders import at, building, seat, session, table

T = make_settings(sim_slot_s=60).timers()

# --- Simulation ----------------------------------------------------------------


def test_simulated_state_is_stable_within_a_slot() -> None:
    assert {simulated_state("x", at(s), 50, T) for s in range(0, 60, 7)} == {
        simulated_state("x", at(0), 50, T)
    }


def test_busier_buildings_never_have_more_open_seats() -> None:
    seats = [f"s{i}" for i in range(400)]
    open_at = {
        b: sum(simulated_state(s, at(0), b, T) is PublicState.OPEN for s in seats)
        for b in (0, 30, 70, 100)
    }
    assert open_at[0] == 400 and open_at[100] == 0
    assert open_at[0] >= open_at[30] >= open_at[70] >= open_at[100]
    for s in seats:  # monotone per seat, not just in aggregate
        if simulated_state(s, at(0), 70, T) is PublicState.OPEN:
            assert simulated_state(s, at(0), 30, T) is PublicState.OPEN


def test_simulation_never_reports_offline() -> None:
    assert PublicState.OFFLINE not in {simulated_state(f"s{i}", at(0), 60, T) for i in range(200)}


# --- Recommendation ------------------------------------------------------------

B = building("b", 30.0, -97.0)
T1 = table("t1", floor=1, x=10, y=10)
T2 = table("t2", floor=1, x=90, y=90)
T3 = table("t3", floor=2, x=10, y=10)


def view(sid: str, tbl: object, pos: int, state: PublicState) -> SeatView:
    return SeatView(seat(sid, tbl, pos), state)  # type: ignore[arg-type]


def test_open_seat_at_the_selected_table_wins() -> None:
    views = [
        view("a", T1, 1, PublicState.OCCUPIED),
        view("b", T1, 2, PublicState.OPEN),
        view("c", T2, 1, PublicState.OPEN),
    ]
    pick = recommend(views, Selection(B, None, T1), [])
    assert pick == Pick(views[1].seat, PublicState.OPEN, RecommendLevel.TABLE)


def test_likely_at_table_beats_open_on_floor_because_each_level_prefers_open_first() -> None:
    views = [view("a", T1, 1, PublicState.LIKELY_OPENING), view("c", T2, 1, PublicState.OPEN)]
    pick = recommend(views, Selection(B, None, T1), [])
    assert isinstance(pick, Pick) and pick.level is RecommendLevel.TABLE
    assert pick.kind is PublicState.LIKELY_OPENING


def test_widens_to_floor_then_picks_the_seat_nearest_the_selected_table() -> None:
    near_table = table("t4", floor=1, x=20, y=20)
    views = [
        view("a", T1, 1, PublicState.OCCUPIED),
        view("far", T2, 1, PublicState.OPEN),
        view("near", near_table, 3, PublicState.OPEN),
    ]
    pick = recommend(views, Selection(B, None, T1), [])
    assert isinstance(pick, Pick) and pick.seat.id == "near" and pick.level is RecommendLevel.FLOOR


def test_widens_to_building_preferring_the_closest_floor() -> None:
    t5 = table("t5", floor=4, x=10, y=10)
    views = [
        view("a", T1, 1, PublicState.OCCUPIED),
        view("f4", t5, 1, PublicState.OPEN),
        view("f2", T3, 1, PublicState.OPEN),
    ]
    pick = recommend(views, Selection(B, 1, None), [])
    assert isinstance(pick, Pick) and pick.seat.id == "f2" and pick.level is RecommendLevel.BUILDING


def test_full_building_points_to_the_nearest_building_with_open_seats() -> None:
    views = [view("a", T1, 1, PublicState.OCCUPIED)]
    near, far = building("near", 30.01, -97.0), building("far", 31.0, -97.0)
    assert recommend(views, Selection(B, None, None), [far, near]) == Full("near")
    assert recommend(views, Selection(B, None, None), []) == Full(None)


# --- Grouping and ranking ------------------------------------------------------


def test_group_of() -> None:
    assert group_of("CH 320M", "chemistry", "CH 320M", "chemistry") is Group.SAME_COURSE
    assert group_of("CH 320M", "chemistry", "CH 301", "chemistry") is Group.RELATED
    assert group_of(None, "chemistry", "CH 301", "chemistry") is Group.RELATED
    assert group_of(None, "general", None, "general") is None
    assert group_of("CH 320M", "chemistry", "M 408C", "mathematics") is None


def test_offered_group_prefers_same_course_and_respects_a_pin() -> None:
    assert offered_group(2, None) is Group.SAME_COURSE
    assert offered_group(0, None) is Group.RELATED
    assert offered_group(2, Group.RELATED) is Group.RELATED


def test_aggregate_counts_by_building_and_floor() -> None:
    assert aggregate([("b", 1), ("b", 1), ("c", 2)]) == [("b", 1, 2), ("c", 2, 1)]


def test_rank_by_score_then_longest_waiting() -> None:
    a, b, c = session("a", started_s=5), session("b", started_s=1), session("c", started_s=0)
    assert [s.id for s in rank([a, b, c], {"a": 90, "b": 50, "c": 50})] == ["a", "c", "b"]


# --- Topic fallback (FR-18, §9) ------------------------------------------------


@pytest.mark.parametrize(
    ("text", "code", "subject"),
    [
        ("dying on ch 320m stereochem mechanisms", "CH 320M", "chemistry"),
        ("orgo 1 exam prep", "CH 320M", "chemistry"),
        ("314 trees hw", "C S 314", "computer science"),
        ("CS314 linked lists", "C S 314", "computer science"),
        ("c s 429 bomb lab", "C S 429", "computer science"),
        ("calc 2 series", "M 408D", "mathematics"),
        ("phy 303k kinematics", "PHY 303K", "physics"),
        ("ch 999 something", "CH 999", "chemistry"),
        ("derivatives practice", None, "mathematics"),
        ("just reading", None, "general"),
    ],
)
def test_normalize_fallback(text: str, code: str | None, subject: str) -> None:
    topic = normalize_fallback(text)
    assert (topic.course_code, topic.subject) == (code, subject)


def test_label_for_known_course_and_unknown_code() -> None:
    assert normalize_fallback("orgo 1").label == "CH 320M · Organic Chemistry I"
    assert normalize_fallback("ch 999").label == "CH 999"
    assert normalize_fallback("derivatives").label == "Mathematics"


def test_keyword_overlap_is_jaccard_scaled() -> None:
    assert keyword_overlap(("a", "b"), ("b", "c")) == 33
    assert keyword_overlap((), ("a",)) == 0


def test_icebreaker_fits_140_chars_and_card_keys() -> None:
    a, b = normalize_fallback("orgo 1"), normalize_fallback("ch 320m")
    text = icebreaker_fallback(a, b)
    assert "CH 320M" in text and len(text) <= 140
    assert card_key_for("computer science") == "computer-science"
    assert card_key_for("general") == "generic"
