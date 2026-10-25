"""Sensor ingest (FR-1..7, D29, D31)."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.domain.seat_engine import apply_reading, led_for, rows_to_store
from app.domain.types import Led, Reading, SeatState
from app.services.context import Context
from app.services.lifecycle import LifecycleService

log = logging.getLogger("ghostseats.readings")


class ReadingsService:
    def __init__(self, ctx: Context, lifecycle: LifecycleService) -> None:
        self._ctx = ctx
        self._lifecycle = lifecycle

    def ingest(self, node_id: str, readings: Sequence[Reading]) -> dict[str, Led]:
        now = self._ctx.clock.now()
        t = self._ctx.timers
        latest = {r.seat_id: r for r in readings}  # a repeated seat id: the last reading wins
        leds: dict[str, Led] = {}
        with self._ctx.repo.tx() as tx:
            tx.touch_node(node_id, now)
            for seat_id in sorted(latest):  # fixed lock order: no deadlocks between nodes
                seat = tx.seat(seat_id)
                if seat is None or seat.is_simulated or seat.node_id != node_id:
                    log.warning(
                        "node %s sent unknown or foreign seat %s; skipped", node_id, seat_id
                    )
                    continue
                before = tx.lock_seat_state(seat_id) or SeatState.never_seen(seat_id)
                reading = latest[seat_id]
                rows = rows_to_store(before, reading, now, t)
                if rows:
                    tx.insert_readings(rows)
                after = apply_reading(before, reading, now, t)
                tx.save_seat_state(after)
                leds[seat_id] = led_for(after, now, t)
            linked = tx.live_sessions_for_seats(list(leds))
        # Presence rules for hosts sitting on these seats (FR-25, 26, 41), after commit.
        for session in linked:
            self._lifecycle.advance_session(session.id)
        return leds
