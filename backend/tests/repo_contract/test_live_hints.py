"""Live hints (D61): both repositories send the same hints for the same writes, on commit only."""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace

import psycopg
import pytest

from app.adapters.hints import CHANNEL, decode, merge
from app.domain.types import (
    InternalState,
    RequestStatus,
    SeatChange,
    SeatState,
    Topic,
    UserChange,
)
from app.services.ports import READS, WRITE_EFFECTS, MapHint, Repository, Tx, UserHint
from tests.fakes import InMemoryRepository
from tests.pg import db_url_for_tests
from tests.repo_contract.test_repository import (
    at,
    new_match,
    new_request,
    new_search,
    new_session,
)

SEAT = frozenset({UserChange.SEAT})


@contextmanager
def hints_from(repo: Repository) -> Iterator[list[MapHint | UserHint]]:
    """Everything committed inside the block, merged as the repository sends it."""
    got: list[MapHint | UserHint] = []
    if isinstance(repo, InMemoryRepository):
        before = len(repo.feed.published)
        yield got
        got += merge([h for batch in repo.feed.published[before:] for h in batch])
        return
    url = db_url_for_tests()
    assert url is not None
    with psycopg.connect(url, autocommit=True) as listener:
        listener.execute(f"LISTEN {CHANNEL}".encode())
        yield got
        received = [decode(n.payload) for n in listener.notifies(timeout=0.3)]
        got += merge([h for h in received if isinstance(h, MapHint | UserHint)])


def user(user_id: str, *changes: UserChange) -> UserHint:
    return UserHint(user_id, frozenset(changes))


def test_every_tx_method_is_classified_as_a_read_or_a_write() -> None:
    methods = {n for n, v in vars(Tx).items() if inspect.isfunction(v) and not n.startswith("_")}
    assert not READS & WRITE_EFFECTS.keys()
    assert methods == READS | WRITE_EFFECTS.keys()


def test_row_writes_hint_their_users_and_resolve_the_host_from_its_session(
    repo: Repository,
) -> None:
    host = new_session()  # alex at s1
    search = new_search()  # priya
    with repo.tx() as tx:
        tx.insert_session(host)
        tx.insert_search(search)
    with hints_from(repo) as got, repo.tx() as tx:
        tx.insert_request(new_request(search, host))
    assert got == [user("alex", UserChange.REQUEST), user("priya", UserChange.REQUEST)]

    with hints_from(repo) as got, repo.tx() as tx:
        tx.update_session(replace(host, muted=True))
        tx.update_search(replace(search, joined_at=at(5)))
        tx.insert_block("sam", "jordan")
    assert got == [
        user("alex", UserChange.SESSION),
        user("jordan", UserChange.BLOCK),
        user("priya", UserChange.SEARCH),
        user("sam", UserChange.BLOCK),
    ]


def test_a_rolled_back_transaction_sends_nothing(repo: Repository) -> None:
    with hints_from(repo) as got, pytest.raises(RuntimeError), repo.tx() as tx:
        tx.insert_session(new_session())
        raise RuntimeError("abandon")
    assert got == []


def test_repeated_writes_in_one_transaction_send_one_hint(repo: Repository) -> None:
    host = new_session()
    with hints_from(repo) as got, repo.tx() as tx:
        tx.insert_session(host)
        tx.update_session(replace(host, muted=True))
        tx.update_session(replace(host, muted=False))
    assert got == [user("alex", UserChange.SESSION)]


def test_writes_that_change_no_view_send_nothing(repo: Repository) -> None:
    with hints_from(repo) as got, repo.tx() as tx:
        tx.touch_node("n1", at(1))
        tx.save_seat_state(
            replace(SeatState.never_seen("s1"), last_seen=at(1)), change=SeatChange.NONE
        )
        tx.cache_topic("k", Topic("CH 320M", "chemistry", ("orgo",), "CH 320M"))
    assert got == []


def test_a_public_seat_change_reaches_the_map_the_table_and_matches_on_the_floor(
    repo: Repository,
) -> None:
    host = new_session()  # alex at s1, table t1
    neighbour = new_session(user="jordan", seat="s4")  # also at t1
    search = new_search()  # priya
    request = new_request(search, host, status=RequestStatus.ACCEPTED)
    with repo.tx() as tx:
        tx.insert_session(host)
        tx.insert_session(neighbour)
        tx.insert_search(search)
        tx.insert_request(request)
        tx.insert_match(new_match(request))  # assigned seat s2, floor 1 of lib
    occupied = replace(
        SeatState.never_seen("s3"),
        state=InternalState.OCCUPIED,
        candidate_state=InternalState.OCCUPIED,
        last_seen=at(1),
    )
    with hints_from(repo) as got, repo.tx() as tx:
        tx.save_seat_state(occupied, change=SeatChange.PUBLIC)
    assert got == [
        MapHint("lib"),
        UserHint("alex", SEAT),
        UserHint("jordan", SEAT),
        UserHint("priya", SEAT),
    ]


def test_presence_alone_reaches_only_the_host_at_that_seat(repo: Repository) -> None:
    with repo.tx() as tx:
        tx.insert_session(new_session())  # alex at s1
        tx.insert_session(new_session(user="jordan", seat="s4"))
    present = replace(SeatState.never_seen("s1"), last_human=at(1), last_seen=at(1))
    with hints_from(repo) as got, repo.tx() as tx:
        tx.save_seat_state(present, change=SeatChange.PRESENCE)
    assert got == [UserHint("alex", SEAT)]


def test_touch_users_hints_with_the_given_change(repo: Repository) -> None:
    with hints_from(repo) as got, repo.tx() as tx:
        tx.touch_users(["sam", "alex"], UserChange.TIME)
    assert got == [user("alex", UserChange.TIME), user("sam", UserChange.TIME)]
