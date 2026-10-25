"""Simulated seats (FR-47): state is a pure function of seat id, time slot and busyness."""

from __future__ import annotations

import hashlib
from datetime import datetime

from app.domain.types import PublicState, Timers

# Of the busy share of seats, this fraction reads ghosted; the rest read occupied.
LIKELY_SHARE_OF_BUSY = 0.12


def unit_hash(seat_id: str, slot: int) -> float:
    digest = hashlib.sha256(f"{seat_id}:{slot}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def simulated_state(seat_id: str, now: datetime, busyness: int, t: Timers) -> PublicState:
    """Deterministic per slot, so every client and every instance sees the same map.

    With busyness b (0-100), a seat is busy with probability b/100. A busy seat reads
    `likely_opening` with probability LIKELY_SHARE_OF_BUSY and `occupied` otherwise. Raising b
    can only move a seat from open to busy, never back: busier buildings have fewer open seats.
    """
    slot = int(now.timestamp() // t.sim_slot.total_seconds())
    u = unit_hash(seat_id, slot)
    busy = busyness / 100
    if u >= busy:
        return PublicState.OPEN
    return PublicState.LIKELY_OPENING if u < busy * LIKELY_SHARE_OF_BUSY else PublicState.OCCUPIED
