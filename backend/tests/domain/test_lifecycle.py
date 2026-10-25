"""Host, search and match transitions (FR-24..42, D15, D18, D22, D24)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from app.domain.lifecycle import (
    EndSession,
    Exhaust,
    KeepSession,
    MatchStep,
    PendingStep,
    SendTo,
    advance_host_session,
    advance_match,
    confirm_due,
    needs_send,
    next_hop,
    pending_step,
)
from app.domain.matching import HostFacts, can_still_receive, host_status
from app.domain.types import EndReason, HiddenReason, HostVisibility, SearchStatus
from tests.conftest import make_settings
from tests.domain.builders import at, match, present, request, search, seat, session

T = make_settings(
    human_fresh_s=10,
    host_end_s=600,
    host_leave_cancel_s=120,
    session_max_s=10800,
    confirm_grace_s=120,
    max_hosts_per_search=3,
    max_requests_per_hour=10,
).timers()
SEAT = seat("s1")


def facts(**over: object) -> HostFacts:
    base: dict[str, object] = {
        "session": session(),
        "seat": SEAT,
        "seat_state": present("s1", last_human_s=100, now_s=100),
        "has_active_match": False,
        "table_open_seats": 1,
    }
    base.update(over)
    return HostFacts(**base)  # type: ignore[arg-type]


# --- FR-24: each condition alone hides the host ------------------------------


def test_findable_when_every_condition_holds() -> None:
    assert host_status(facts(), at(105), T) == (HostVisibility.FINDABLE, None)


@pytest.mark.parametrize(
    ("over", "reason"),
    [
        ({"session": session(topic=False)}, HiddenReason.NEEDS_TOPIC),
        ({"session": session(expires_s=105)}, HiddenReason.CONFIRM_PENDING),
        ({"has_active_match": True}, HiddenReason.IN_MATCH),
        ({"seat_state": present("s1", last_human_s=94, now_s=105)}, HiddenReason.AWAY),
        ({"session": session(muted=True)}, HiddenReason.MUTED),
        ({"table_open_seats": 0}, HiddenReason.TABLE_FULL),
    ],
)
def test_each_failing_condition_hides_the_host(
    over: dict[str, object], reason: HiddenReason
) -> None:
    assert host_status(facts(**over), at(105), T) == (HostVisibility.HIDDEN, reason)


def test_ended_session_is_ended() -> None:
    assert host_status(facts(session=session(ended=True)), at(105), T)[0] is HostVisibility.ENDED


def test_simulated_host_is_findable_without_presence() -> None:
    f = facts(seat=seat("sim", simulated=True), seat_state=None, table_open_seats=0)
    assert host_status(f, at(10**6), T) == (HostVisibility.FINDABLE, None)


def test_full_table_keeps_a_pending_request_but_absence_does_not() -> None:
    assert can_still_receive(HostVisibility.HIDDEN, HiddenReason.TABLE_FULL)
    assert not can_still_receive(HostVisibility.HIDDEN, HiddenReason.AWAY)
    assert not can_still_receive(HostVisibility.ENDED, None)


# --- Host session end and confirmation (FR-26, FR-27) ------------------------


def test_session_ends_after_exactly_host_end_s_with_no_person() -> None:
    state = present("s1", last_human_s=0, now_s=500)  # backpack still there, readings flowing
    assert advance_host_session(session(), SEAT, state, at(599.999), T) == KeepSession()
    assert advance_host_session(session(), SEAT, state, at(600), T) == EndSession(
        EndReason.NO_PERSON
    )


def test_confirm_prompt_once_then_unconfirmed_after_grace() -> None:
    s = session(expires_s=1000)
    state = present("s1", last_human_s=1100, now_s=1100)
    assert advance_host_session(s, SEAT, state, at(999), T) == KeepSession(notify_confirm=False)
    assert advance_host_session(s, SEAT, state, at(1000), T) == KeepSession(notify_confirm=True)
    told = replace(s, confirm_notified_at=at(1000))
    assert advance_host_session(told, SEAT, state, at(1050), T) == KeepSession(notify_confirm=False)
    assert advance_host_session(told, SEAT, state, at(1120), T) == EndSession(EndReason.UNCONFIRMED)


def test_confirm_due_window() -> None:
    s = session(expires_s=1000)
    assert not confirm_due(s, at(999), T)
    assert confirm_due(s, at(1000), T)
    assert not confirm_due(s, at(1120), T)


def test_simulated_sessions_never_end() -> None:
    sim = seat("sim", simulated=True)
    assert advance_host_session(session(expires_s=0), sim, None, at(10**7), T) == KeepSession()


# --- Search cascade (FR-31..35, D15, D19) ------------------------------------


def test_pending_request_expires_exactly_at_timeout_then_skips_absent_host() -> None:
    req = request(expires_s=120)
    assert pending_step(req, True, at(119.999)) is PendingStep.WAIT
    assert pending_step(req, True, at(120)) is PendingStep.EXPIRE
    assert pending_step(req, False, at(50)) is PendingStep.SKIP


def test_needs_send_only_when_joined_active_and_nothing_pending() -> None:
    assert needs_send(search(), None)
    assert not needs_send(search(joined=False), None)
    assert not needs_send(search(), request())
    assert not needs_send(search(status=SearchStatus.EXHAUSTED), None)


def test_next_hop_skips_tried_hosts_in_rank_order() -> None:
    assert next_hop(search(tried=("a",)), ["a", "b", "c"], 0, T) == SendTo("b")


def test_exhausted_after_max_hosts_even_if_more_exist() -> None:
    assert next_hop(search(tried=("a", "b", "c")), ["d"], 0, T) == Exhaust()


def test_exhausted_when_no_untried_host_remains() -> None:
    assert next_hop(search(tried=("a",)), ["a"], 0, T) == Exhaust()


def test_exhausted_at_the_hourly_request_cap() -> None:
    assert next_hop(search(), ["a"], 10, T) == Exhaust()


# --- Matches (FR-41, FR-42) ---------------------------------------------------


def test_match_cancels_after_exactly_two_minutes_without_the_host() -> None:
    state = present("s1", last_human_s=0, now_s=100)
    assert advance_match(match(), state, at(119.999), T) is MatchStep.KEEP
    assert advance_match(match(), state, at(120), T) is MatchStep.CANCEL


def test_match_expires_at_timeout_before_cancel_is_considered() -> None:
    state = present("s1", last_human_s=0)
    assert advance_match(match(expires_s=100), state, at(100), T) is MatchStep.EXPIRE


def test_finished_match_never_changes() -> None:
    from app.domain.types import MatchStatus

    done = match(status=MatchStatus.COMPLETED)
    assert advance_match(done, None, at(10**6), T) is MatchStep.KEEP
