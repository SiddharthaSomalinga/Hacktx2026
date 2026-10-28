"""Repository conformance (D3): InMemoryRepository and PostgresRepository behave identically."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import timedelta

import pytest

from app.domain.types import (
    EndReason,
    Group,
    HostSession,
    InternalState,
    Match,
    MatchStatus,
    OutboxKind,
    OutboxMessage,
    RequestStatus,
    Search,
    SearchStatus,
    SeatState,
    StoredReading,
    StudyRequest,
    Topic,
)
from app.services.ports import Conflict, Lock, Repository
from tests.fakes import T0

OFFLINE = timedelta(seconds=30)


def at(seconds: float):  # type: ignore[no-untyped-def]
    return T0 + timedelta(seconds=seconds)


def new_session(user: str = "alex", seat: str = "s1", **over: object) -> HostSession:
    base = HostSession(
        id=str(uuid.uuid4()), user_id=user, seat_id=seat, topic_raw="orgo", course_code="CH 320M",
        subject="chemistry", keywords=("orgo", "exam"), about_me=None, open=True, muted=False,
        started_at=at(0), expires_at=at(10800), ended_at=None, end_reason=None,
        confirm_notified_at=None, label="CH 320M · Organic Chemistry I",
    )  # fmt: skip
    return replace(base, **over)  # type: ignore[arg-type]


def new_search(seeker: str = "priya", **over: object) -> Search:
    base = Search(
        id=str(uuid.uuid4()), seeker_id=seeker, topic_raw="orgo 1", course_code="CH 320M",
        subject="chemistry", keywords=("orgo",), label="CH 320M", offered_group=Group.SAME_COURSE,
        status=SearchStatus.ACTIVE, tried_session_ids=(), created_at=at(0), joined_at=None,
    )  # fmt: skip
    return replace(base, **over)  # type: ignore[arg-type]


def new_request(search: Search, session: HostSession, **over: object) -> StudyRequest:
    base = StudyRequest(
        str(uuid.uuid4()), search.id, search.seeker_id, session.id, RequestStatus.PENDING,
        at(0), at(120),
    )  # fmt: skip
    return replace(base, **over)  # type: ignore[arg-type]


def new_match(request: StudyRequest, **over: object) -> Match:
    base = Match(
        str(uuid.uuid4()), request.id, request.seeker_id, request.host_session_id, "hi",
        "chemistry", "s2", MatchStatus.ACTIVE, at(0), at(1200), None,
    )  # fmt: skip
    return replace(base, **over)  # type: ignore[arg-type]


# --- places and sensing ---------------------------------------------------------


def test_places(repo: Repository) -> None:
    with repo.read() as tx:
        assert {b.id for b in tx.buildings()} == {"lib", "sim"}
        assert {t.id for t in tx.tables("lib")} == {"t1", "t2"}
        assert len(tx.seats("lib")) == 10 and len(tx.seats()) == 14
        s1 = tx.seat("s1")
        assert s1 is not None and (s1.building_id, s1.floor, s1.x, s1.node_id) == (
            "lib",
            1,
            20,
            "n1",
        )
        assert tx.seat("nope") is None


def test_seat_state_round_trip(repo: Repository) -> None:
    state = replace(
        SeatState.never_seen("s1"), state=InternalState.AWAY, candidate_state=InternalState.AWAY,
        candidate_since=at(1), state_since=at(2), away_since=at(1), last_object=at(3),
        last_human=at(0), last_seen=at(3), blink_until=at(60),
    )  # fmt: skip
    with repo.tx() as tx:
        tx.save_seat_state(state)
    with repo.read() as tx:
        assert tx.seat_states(["s1", "s2"])["s1"] == state
    with repo.tx() as tx:
        assert tx.lock_seat_state("s1") == state


def test_readings_round_trip_in_time_order(repo: Repository) -> None:
    rows = [
        StoredReading("s1", at(0), True, True, False),
        StoredReading("s1", at(30), False, None, None),
        StoredReading("s2", at(5), True, False, False),
    ]
    with repo.tx() as tx:
        tx.insert_readings(rows)
    with repo.read() as tx:
        assert tx.readings(["s1", "s2"], at(100)) == sorted(rows, key=lambda r: (r.seat_id, r.time))
        assert tx.readings(["s1"], at(30)) == rows[:1]


def test_rollback_on_exception(repo: Repository) -> None:
    with pytest.raises(RuntimeError), repo.tx() as tx:
        tx.save_seat_state(replace(SeatState.never_seen("s1"), last_seen=at(9)))
        raise RuntimeError("boom")
    with repo.read() as tx:
        assert tx.seat_states(["s1"])["s1"].last_seen is None


# --- users, topics, safety ----------------------------------------------------


def test_users_topics_and_blocks(repo: Repository) -> None:
    topic = Topic("CH 320M", "chemistry", ("orgo", "stereo"), "CH 320M · Organic Chemistry I")
    with repo.tx() as tx:
        tx.cache_topic("orgo", topic)
        tx.cache_topic("orgo", replace(topic, subject="other"))  # first write wins
        tx.insert_block("alex", "priya")
        tx.insert_block("alex", "priya")  # idempotent
        tx.insert_report("sam", "alex", "rude", at(0))
    with repo.read() as tx:
        assert [u.id for u in tx.demo_users()] == ["alex", "jordan", "priya", "sam"]
        assert tx.user("simhost") is not None and not tx.user("simhost").is_demo  # type: ignore[union-attr]
        assert tx.cached_topic("orgo") == topic
        assert tx.blocked_with("alex") == {"priya"} and tx.blocked_with("priya") == {"alex"}


# --- uniqueness rules (partial unique indexes) -----------------------------------


def test_one_live_session_per_user_and_per_seat(repo: Repository) -> None:
    first = new_session()
    with repo.tx() as tx:
        tx.insert_session(first)
    for dup in (new_session(seat="s2"), new_session(user="jordan")):
        with pytest.raises(Conflict), repo.tx() as tx:
            tx.insert_session(dup)
    with repo.tx() as tx:
        tx.update_session(replace(first, ended_at=at(5), end_reason=EndReason.TOGGLED_OFF))
        tx.insert_session(new_session())  # allowed once the first has ended
    with repo.read() as tx:
        assert len(tx.live_sessions()) == 1
        assert tx.live_sessions_for_seats(["s1"])[0].user_id == "alex"


def test_one_active_search_one_pending_request_one_active_match(repo: Repository) -> None:
    session = new_session()
    search = new_search()
    request = new_request(search, session)
    with repo.tx() as tx:
        tx.insert_session(session)
        tx.insert_search(search)
        tx.insert_request(request)
        tx.insert_match(new_match(request))
    with pytest.raises(Conflict), repo.tx() as tx:
        tx.insert_search(new_search())
    with pytest.raises(Conflict), repo.tx() as tx:
        tx.insert_request(new_request(search, session))
    with pytest.raises(Conflict), repo.tx() as tx:
        tx.insert_match(new_match(request, id=str(uuid.uuid4()), request_id=request.id))


def test_conflict_rolls_back_the_whole_unit(repo: Repository) -> None:
    with repo.tx() as tx:
        tx.insert_search(new_search())
    with pytest.raises(Conflict), repo.tx() as tx:
        tx.insert_block("sam", "jordan")
        tx.insert_search(new_search())
    with repo.read() as tx:
        assert tx.blocked_with("sam") == set()


# --- lookups ----------------------------------------------------------------------


def test_lookups_and_round_trips(repo: Repository) -> None:
    session = new_session()
    search = new_search(tried_session_ids=(session.id,), joined_at=at(1))
    request = new_request(search, session)
    with repo.tx() as tx:
        tx.insert_session(session)
        tx.insert_search(search)
        tx.insert_request(request)
    with repo.tx() as tx:
        assert tx.session(session.id, Lock.WAIT) == session
        assert tx.live_session_for_user("alex", Lock.WAIT) == session
        assert tx.search(search.id, Lock.WAIT) == search
        assert tx.active_search_for_user("priya") == search
        assert tx.request(request.id, Lock.WAIT) == request
        assert tx.pending_request_for_search(search.id) == request
        assert tx.pending_requests_for_session(session.id) == [request]
        assert tx.count_requests_since("priya", at(0)) == 1
        assert tx.count_requests_since("priya", at(1)) == 0
        tx.update_request(replace(request, status=RequestStatus.ACCEPTED))
        match = new_match(request)
        tx.insert_match(match)
        tx.update_search(replace(search, status=SearchStatus.MATCHED))
    with repo.read() as tx:
        assert tx.match(match.id) == match
        assert tx.active_match_for_session(session.id) == match
        assert tx.active_match_for_seeker("priya") == match
        assert tx.match_for_search(search.id) == match


@pytest.mark.parametrize("bad", ["", "not-a-uuid", "123", "'; DROP TABLE users; --"])
def test_malformed_ids_are_not_found(repo: Repository, bad: str) -> None:
    with repo.read() as tx:
        assert tx.session(bad) is None
        assert tx.search(bad) is None
        assert tx.request(bad) is None
        assert tx.match(bad) is None
        assert tx.seat(bad) is None
        assert tx.user(bad) is None


# --- push and outbox --------------------------------------------------------------


def test_subscriptions_and_outbox(repo: Repository) -> None:
    with repo.tx() as tx:
        tx.upsert_subscription("alex", "https://e/1", "k", "a", at(0))
        tx.upsert_subscription(
            "alex", "https://e/1", "k2", "a2", at(1)
        )  # same device re-subscribes
        tx.upsert_subscription("priya", "https://e/2", "k", "a", at(0))
        tx.delete_subscription("https://e/2", "alex")  # not alex's: untouched
        tx.enqueue(
            [
                OutboxMessage("alex", OutboxKind.REQUEST_RECEIVED, {"title": "t", "url": "/host"}),
                OutboxMessage("priya", OutboxKind.SEARCH_EXHAUSTED, {"title": "x"}),
            ],
            at(0),
        )
    with repo.tx() as tx:
        subs = tx.subscriptions_for("alex")
        assert [(s.endpoint, s.p256dh) for s in subs] == [("https://e/1", "k2")]
        assert len(tx.subscriptions_for("priya")) == 1
        assert tx.outbox_unsent() == 2
        rows = tx.claim_outbox(10)
        assert [r.message.kind for r in rows] == ["request_received", "search_exhausted"]
        assert rows[0].message.payload == {"title": "t", "url": "/host"}
        tx.mark_outbox(rows[0].id, at(5), 1)
        tx.mark_outbox(rows[1].id, None, 1)
    with repo.tx() as tx:
        left = tx.claim_outbox(10)
        assert [(r.message.kind, r.attempts) for r in left] == [("search_exhausted", 1)]
        assert tx.outbox_unsent() == 1  # the retried row still counts
        tx.delete_subscription("https://e/2")
        assert tx.subscriptions_for("priya") == []


# --- scheduler queries --------------------------------------------------------------


def test_due_queries(repo: Repository) -> None:
    present = replace(SeatState.never_seen("s1"), last_human=at(100), last_seen=at(100))
    gone = replace(SeatState.never_seen("s2"), last_human=at(0), last_seen=at(100))
    host_here, host_gone = new_session(), new_session(user="jordan", seat="s2")
    sim_host = new_session(user="simhost", seat="t2-s1", expires_at=at(0))
    s_ok, s_gone = new_search(), new_search(seeker="sam")
    r_ok = new_request(s_ok, host_here, expires_at=at(500))
    r_gone = new_request(s_gone, host_gone, expires_at=at(500))
    with repo.tx() as tx:
        tx.save_seat_state(present)
        tx.save_seat_state(gone)
        for s in (host_here, host_gone, sim_host):
            tx.insert_session(s)
        for q in (s_ok, s_gone):
            tx.insert_search(q)
        tx.insert_request(r_ok)
        tx.insert_request(r_gone)
        tx.insert_match(new_match(r_ok, seeker_id="priya", expires_at=at(1000)))
    with repo.read() as tx:
        assert tx.due_search_ids(at(105), at(95)) == [s_gone.id]
        assert set(tx.due_search_ids(at(500), at(95))) == {s_ok.id, s_gone.id}
        assert tx.due_match_ids(at(105), at(-10)) == []
        assert len(tx.due_match_ids(at(1000), at(-10))) == 1
        assert tx.due_session_ids(at(105), at(50)) == [host_gone.id]  # simulated never due


# --- history (FR-49, D31) -------------------------------------------------------------


def test_history_matches_the_reference_semantics(repo: Repository) -> None:
    """s1 open 0-30 min, occupied after; s2 open from 15 min, offline marker at 45 min;
    s3 never reported. One-hour window starting at T0."""
    rows = [
        StoredReading("s1", at(0), True, False, False),
        StoredReading("s1", at(1800), True, True, True),
        StoredReading("s2", at(900), True, False, False),
        StoredReading("s2", at(2700), False, None, None),
    ]
    with repo.tx() as tx:
        tx.insert_readings(rows)
        tx.save_seat_state(replace(SeatState.never_seen("s1"), last_seen=at(3600)))
        tx.save_seat_state(replace(SeatState.never_seen("s2"), last_seen=at(2670)))
    points = repo.history("lib", at(0), at(3600), OFFLINE)
    assert len(points) == 1
    hour, avg = points[0]
    assert hour == at(0)
    # s1: 1800 s open; s2: 900→2700 = 1800 s open → 3600 open-seconds / 3600 = 1.0
    assert avg == pytest.approx(1.0)


def test_history_carries_state_in_from_before_the_window_and_caps_silent_seats(
    repo: Repository,
) -> None:
    with repo.tx() as tx:
        tx.insert_readings([StoredReading("s1", at(-7200), True, False, False)])
        tx.save_seat_state(replace(SeatState.never_seen("s1"), last_seen=at(1770)))
    points = repo.history("lib", at(0), at(7200), OFFLINE)
    assert [round(p[1], 4) for p in points] == [0.5, 0.0]  # open until last_seen + 30 s = 1800


def test_history_partial_current_hour(repo: Repository) -> None:
    with repo.tx() as tx:
        tx.insert_readings([StoredReading("s1", at(0), True, False, False)])
        tx.save_seat_state(replace(SeatState.never_seen("s1"), last_seen=at(900)))
    points = repo.history("lib", at(0), at(900), OFFLINE)
    assert points == [(at(0), pytest.approx(1.0))]  # 900 open seconds of 900 elapsed
