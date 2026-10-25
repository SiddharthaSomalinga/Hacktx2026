"""Write HISTORY_WINDOW_H of change-only readings for every seat (FR-49, D31).

Each seat's sensed state per 10-minute slot follows the building's busyness through the same
deterministic hash the simulation uses, so the chart has realistic, reproducible shape. Only
changes are written, exactly like live ingest. It never deletes anything: seats that already
have readings in the window (real sensor data, or an earlier seed) are skipped, so re-running
is safe on a live database.

    uv run python -m scripts.seed_history
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

import psycopg

from app.config import get_settings
from app.domain.simulation import unit_hash

SLOT = timedelta(minutes=10)


def sensed(seat_id: str, slot: int, busyness: int) -> tuple[bool, bool]:
    """(object_present, human_present) for one seat in one slot."""
    u = unit_hash(f"history:{seat_id}", slot)
    busy = busyness / 100
    if u >= busy:
        return (False, False)
    return (True, False) if u < busy * 0.12 else (True, True)


def main() -> int:
    settings = get_settings()
    now = datetime.now(UTC)
    start = now - timedelta(hours=settings.history_window_h + 1)
    first_slot = int(start.timestamp() // SLOT.total_seconds())
    last_slot = int(now.timestamp() // SLOT.total_seconds())
    with psycopg.connect(settings.database_url) as conn:
        window_start = datetime.fromtimestamp(first_slot * SLOT.total_seconds(), UTC)
        seats = conn.execute(
            b"""SELECT s.id, b.busyness FROM seats s JOIN tables t ON t.id = s.table_id
                JOIN buildings b ON b.id = t.building_id
                WHERE NOT EXISTS (SELECT 1 FROM seat_readings r
                                  WHERE r.seat_id = s.id AND r.time >= %s)""",
            (window_start,),
        ).fetchall()
        rows: list[tuple[datetime, str, bool, bool]] = []
        for seat_id, busyness in seats:
            previous: tuple[bool, bool] | None = None
            for slot in range(first_slot, last_slot):
                current = sensed(seat_id, slot, busyness)
                if current != previous:
                    at = datetime.fromtimestamp(slot * SLOT.total_seconds(), UTC)
                    rows.append((at, seat_id, *current))
                    previous = current
        with conn.transaction(), conn.cursor() as cur:
            cur.executemany(
                b"INSERT INTO seat_readings (time, seat_id, online, object_present, human_present)"
                b" VALUES (%s, %s, true, %s, %s)",
                rows,
            )
    print(f"seeded {len(rows)} change rows for {len(seats)} seats without readings")
    return 0


if __name__ == "__main__":
    sys.exit(main())
