"""History SQL (FR-49, D31) and Timescale policies (D32).

Readings are change-only, so a seat's state at time t is its latest row at or before t. The
query rebuilds each seat's intervals with a window function, clips them to the window and to
`last_seen + OFFLINE_S` (after that the seat's state is unknown), and sums open seconds per
hour. It returns the same numbers as the in-memory reference implementation; the repository
conformance suite checks that.
"""

from __future__ import annotations

HISTORY_SQL = """
WITH seats_b AS (
  SELECT s.id, ss.last_seen
  FROM seats s
  JOIN tables t ON t.id = s.table_id
  LEFT JOIN seat_state ss ON ss.seat_id = s.id
  WHERE t.building_id = %(building)s
),
rows_in AS (
  -- the row in force at the start of the window, per seat ...
  SELECT x.seat_id, x.time, x.online, x.object_present, x.human_present
  FROM seats_b sb
  CROSS JOIN LATERAL (
    SELECT r.seat_id, r.time, r.online, r.object_present, r.human_present
    FROM seat_readings r
    WHERE r.seat_id = sb.id AND r.time <= %(since)s
    ORDER BY r.time DESC
    LIMIT 1
  ) x
  UNION ALL
  -- ... and every change inside the window
  SELECT r.seat_id, r.time, r.online, r.object_present, r.human_present
  FROM seat_readings r
  WHERE r.seat_id IN (SELECT id FROM seats_b)
    AND r.time > %(since)s AND r.time < %(until)s
),
intervals AS (
  SELECT
    greatest(i.time, %(since)s) AS start_at,
    least(
      coalesce(lead(i.time) OVER (PARTITION BY i.seat_id ORDER BY i.time), %(until)s),
      coalesce(sb.last_seen + %(offline)s, %(until)s),
      %(until)s
    ) AS stop_at
  FROM rows_in i
  JOIN seats_b sb ON sb.id = i.seat_id
  WHERE i.online AND NOT i.object_present AND NOT i.human_present
),
hours AS (
  SELECT h AS hour_at, least(h + interval '1 hour', %(until)s) AS hour_end
  FROM generate_series(%(since)s::timestamptz, %(until)s::timestamptz - interval '1 microsecond',
                       interval '1 hour') AS h
)
SELECT
  hours.hour_at AS hour,
  coalesce(sum(extract(epoch FROM least(iv.stop_at, hours.hour_end)
                                  - greatest(iv.start_at, hours.hour_at))), 0)
    / extract(epoch FROM hours.hour_end - hours.hour_at) AS open_avg
FROM hours
LEFT JOIN intervals iv
  ON iv.stop_at > hours.hour_at AND iv.start_at < hours.hour_end AND iv.stop_at > iv.start_at
GROUP BY hours.hour_at, hours.hour_end
ORDER BY hours.hour_at
"""


def policy_statements(retention_days: int) -> list[str]:
    """Compression of raw readings older than a day, and retention after `retention_days`."""
    if retention_days <= 0:
        raise ValueError("retention_days must be positive")
    return [
        """ALTER TABLE seat_readings SET (
             timescaledb.compress,
             timescaledb.compress_segmentby = 'seat_id',
             timescaledb.compress_orderby = 'time DESC')""",
        "SELECT add_compression_policy('seat_readings', INTERVAL '1 day', if_not_exists => true)",
        "SELECT remove_retention_policy('seat_readings', if_exists => true)",
        f"SELECT add_retention_policy('seat_readings', INTERVAL '{int(retention_days)} days')",
    ]
