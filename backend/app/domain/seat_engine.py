"""The seat state engine (FR-1..7) and presence rules (D18). Pure: `now` is always a parameter."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta

from app.domain.types import (
    InternalState,
    Led,
    PublicState,
    Reading,
    SeatState,
    StoredReading,
    Timers,
)

NEVER = timedelta.max


def candidate_of(reading: Reading) -> InternalState:
    """FR-2: a person means occupied; belongings alone mean away; nothing means open."""
    if reading.human_present:
        return InternalState.OCCUPIED
    if reading.object_present:
        return InternalState.AWAY
    return InternalState.OPEN


def apply_reading(s: SeatState, reading: Reading, now: datetime, t: Timers) -> SeatState:
    """Fold one reading into the seat's state, committing a candidate after DEBOUNCE_S (FR-3)."""
    candidate = candidate_of(reading)
    s = replace(
        s,
        last_seen=now,
        last_object=now if reading.object_present else s.last_object,
        last_human=now if reading.human_present else s.last_human,
    )
    if candidate != s.candidate_state or s.candidate_since is None:
        s = replace(s, candidate_state=candidate, candidate_since=now)
    assert s.candidate_since is not None
    if s.candidate_state != s.state and now - s.candidate_since >= t.debounce:
        s = replace(
            s,
            state=s.candidate_state,
            state_since=now,
            away_since=s.candidate_since if s.candidate_state is InternalState.AWAY else None,
        )
    return s


def is_offline(s: SeatState, now: datetime, t: Timers) -> bool:
    return s.last_seen is None or now - s.last_seen >= t.offline


def public_state(s: SeatState, now: datetime, t: Timers) -> PublicState:
    """FR-4..6. Away duration is used here and never exposed."""
    if is_offline(s, now, t):
        return PublicState.OFFLINE
    if s.state is InternalState.OPEN:
        return PublicState.OPEN
    if s.state is InternalState.OCCUPIED:
        return PublicState.OCCUPIED
    assert s.away_since is not None
    return PublicState.LIKELY_OPENING if now - s.away_since >= t.ghost else PublicState.OCCUPIED


_LED = {
    PublicState.OPEN: Led.GREEN,
    PublicState.OCCUPIED: Led.RED,
    PublicState.LIKELY_OPENING: Led.YELLOW,
    PublicState.OFFLINE: Led.OFF,
}


def led_for(s: SeatState, now: datetime, t: Timers) -> Led:
    """FR-7. A blink window overrides the state color."""
    if is_offline(s, now, t):
        return Led.OFF
    if s.blink_until is not None and s.blink_until > now:
        return Led.BLUE_BLINK
    return _LED[public_state(s, now, t)]


def human_present_now(s: SeatState, now: datetime, t: Timers) -> bool:
    """A person counts as present if seen within HUMAN_FRESH_S. Belongings never count (D18)."""
    return s.last_human is not None and now - s.last_human <= t.human_fresh


def absent_for(s: SeatState, now: datetime) -> timedelta:
    """How long since a person was last seen on this seat; NEVER if no person ever was."""
    return NEVER if s.last_human is None else now - s.last_human


def rows_to_store(s: SeatState, reading: Reading, now: datetime, t: Timers) -> list[StoredReading]:
    """Change-only storage (D31), computed from the state *before* this reading is applied.

    The previous stored pair is recovered from the last-seen timestamps: a sensor was true in
    the previous reading exactly when its `last_*` equals `last_seen`. After an offline gap the
    seat gets an `online=False` marker at `last_seen + OFFLINE_S`, and the new pair is stored.
    """
    rows: list[StoredReading] = []
    gap = s.last_seen is not None and now - s.last_seen > t.offline
    if gap:
        assert s.last_seen is not None
        rows.append(StoredReading(s.seat_id, s.last_seen + t.offline, False, None, None))
    previous: tuple[bool, bool] | None = None
    if s.last_seen is not None and not gap:
        previous = (s.last_object == s.last_seen, s.last_human == s.last_seen)
    current = (reading.object_present, reading.human_present)
    if previous != current:
        rows.append(StoredReading(s.seat_id, now, True, *current))
    return rows
