"""Seat engine boundaries (FR-2..7, D18, D31). Each test pins one threshold exactly."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from app.domain.seat_engine import (
    NEVER,
    absent_for,
    apply_reading,
    candidate_of,
    human_present_now,
    led_for,
    public_state,
    rows_to_store,
    seat_change,
)
from app.domain.types import InternalState, Led, PublicState, Reading, SeatChange, SeatState
from tests.conftest import make_settings
from tests.fakes import T0

T = make_settings(debounce_s=5, ghost_s=30, offline_s=30, human_fresh_s=10).timers()

PERSON = Reading("s1", object_present=True, human_present=True)
BAG = Reading("s1", object_present=True, human_present=False)
EMPTY = Reading("s1", object_present=False, human_present=False)


def at(seconds: float) -> datetime:
    return T0 + timedelta(seconds=seconds)


def feed(readings: list[tuple[float, Reading]], s: SeatState | None = None) -> SeatState:
    s = s or SeatState.never_seen("s1")
    for seconds, reading in readings:
        s = apply_reading(s, reading, at(seconds), T)
    return s


@pytest.mark.parametrize(
    ("reading", "expected"),
    [
        (PERSON, InternalState.OCCUPIED),
        (BAG, InternalState.AWAY),
        (EMPTY, InternalState.OPEN),
        (Reading("s1", False, True), InternalState.OCCUPIED),
    ],
)
def test_candidate_of(reading: Reading, expected: InternalState) -> None:
    assert candidate_of(reading) is expected


def test_never_seen_seat_is_offline_with_led_off() -> None:
    s = SeatState.never_seen("s1")
    assert public_state(s, at(0), T) is PublicState.OFFLINE
    assert led_for(s, at(0), T) is Led.OFF


def test_candidate_commits_exactly_at_debounce() -> None:
    s = feed([(0, PERSON), (4.999, PERSON)])
    assert s.state is InternalState.OPEN
    s = apply_reading(s, PERSON, at(5), T)
    assert s.state is InternalState.OCCUPIED
    assert s.state_since == at(5)


def test_flapping_candidate_restarts_the_debounce() -> None:
    s = feed([(0, PERSON), (3, EMPTY), (4, PERSON), (8, PERSON)])
    assert s.state is InternalState.OPEN  # PERSON candidate restarted at 4, needs until 9
    assert apply_reading(s, PERSON, at(9), T).state is InternalState.OCCUPIED


def test_away_reads_occupied_until_exactly_ghost_s() -> None:
    s = feed([(0, PERSON), (5, PERSON), (10, BAG), (15, BAG)])
    assert s.state is InternalState.AWAY
    assert s.away_since == at(10)  # when the bag-only candidate began, not when it committed
    assert public_state(s, at(39.999), T) is PublicState.OCCUPIED
    assert public_state(s, at(40), T) is PublicState.LIKELY_OPENING
    assert led_for(s, at(39.999), T) is Led.RED
    assert led_for(s, at(40), T) is Led.YELLOW


def test_returning_person_clears_away_since() -> None:
    s = feed([(0, BAG), (5, BAG), (10, PERSON), (15, PERSON)])
    assert s.state is InternalState.OCCUPIED
    assert s.away_since is None


def test_offline_exactly_at_offline_s_and_wins_over_everything() -> None:
    s = feed([(0, EMPTY), (5, EMPTY)])
    s = replace(s, blink_until=at(1000))
    assert public_state(s, at(34.999), T) is PublicState.OPEN
    assert public_state(s, at(35), T) is PublicState.OFFLINE
    assert led_for(s, at(35), T) is Led.OFF


def test_blink_overrides_color_until_blink_until() -> None:
    s = replace(feed([(0, PERSON), (5, PERSON)]), blink_until=at(20))
    assert led_for(s, at(19.999), T) is Led.BLUE_BLINK
    assert led_for(s, at(20), T) is Led.RED
    assert public_state(s, at(10), T) is PublicState.OCCUPIED  # blink never changes public state


def test_presence_is_fresh_for_exactly_human_fresh_s() -> None:
    s = feed([(0, PERSON)])
    assert human_present_now(s, at(10), T)
    assert not human_present_now(s, at(10.001), T)


def test_belongings_never_count_as_presence() -> None:
    s = feed([(0, BAG), (1, BAG)])
    assert not human_present_now(s, at(1), T)
    assert absent_for(s, at(1)) == NEVER
    s = feed([(2, PERSON), (3, BAG)], s)
    assert absent_for(s, at(13)) == timedelta(seconds=11)


# --- change-only storage (D31) ----------------------------------------------


def test_first_reading_is_stored() -> None:
    rows = rows_to_store(SeatState.never_seen("s1"), BAG, at(0), T)
    assert [(r.time, r.online, r.object_present, r.human_present) for r in rows] == [
        (at(0), True, True, False)
    ]


def test_identical_readings_store_nothing() -> None:
    s = feed([(0, BAG)])
    assert rows_to_store(s, BAG, at(2), T) == []


def test_a_change_in_either_sensor_is_stored() -> None:
    s = feed([(0, BAG)])
    assert len(rows_to_store(s, PERSON, at(2), T)) == 1
    s = feed([(0, PERSON)])
    assert len(rows_to_store(s, EMPTY, at(2), T)) == 1


def test_gap_longer_than_offline_s_writes_a_marker_then_the_reading() -> None:
    s = feed([(0, BAG)])
    rows = rows_to_store(s, BAG, at(31), T)
    assert [(r.time, r.online) for r in rows] == [(at(30), False), (at(31), True)]


def test_gap_of_exactly_offline_s_is_not_a_gap() -> None:
    s = feed([(0, BAG)])
    assert rows_to_store(s, BAG, at(30), T) == []


def _fold(readings: list[tuple[float, Reading]]) -> SeatState:
    s = SeatState.never_seen("s1")
    for t, r in readings:
        s = apply_reading(s, r, T0 + timedelta(seconds=t), T)
    return s


@pytest.mark.parametrize(
    ("history", "reading", "at", "expected"),
    [
        # First reading ever: offline -> open is public.
        ([], EMPTY, 0, SeatChange.PUBLIC),
        # A heartbeat that changes nothing.
        ([(0, EMPTY)], EMPTY, 2, SeatChange.NONE),
        # A person appears but the debounce hasn't passed: only presence changed.
        ([(0, EMPTY)], PERSON, 2, SeatChange.PRESENCE),
        # The same person, once the debounce commits occupied: public.
        ([(0, EMPTY), (2, PERSON)], PERSON, 7, SeatChange.PUBLIC),
        # Still present and occupied: nothing new.
        ([(0, EMPTY), (2, PERSON), (7, PERSON)], PERSON, 9, SeatChange.NONE),
        # The person leaves the bag: away commits but stays public occupied (GHOST_S).
        ([(0, PERSON), (5, PERSON), (6, BAG)], BAG, 11, SeatChange.NONE),
        # Back after an offline gap: offline -> occupied is public.
        ([(0, PERSON), (5, PERSON)], PERSON, 40, SeatChange.PUBLIC),
    ],
)
def test_seat_change_says_what_others_can_see(
    history: list[tuple[float, Reading]], reading: Reading, at: float, expected: SeatChange
) -> None:
    before = _fold(history)
    now = T0 + timedelta(seconds=at)
    assert seat_change(before, apply_reading(before, reading, now, T), now, T) is expected
