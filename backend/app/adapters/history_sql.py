"""History SQL (FR-49, D31, D33) and Timescale policies (D32).

The query itself is the `open_hourly` SQL function in sql/schema.sql: readings are change-only,
so a seat's state at time t is its latest row at or before t. The function rebuilds each seat's
intervals with lead() over all rows, keeps the open ones, clips them to the window and to
`last_seen + OFFLINE_S`, and sums open seconds per hour. The API and the rollup job both call
it; the repository conformance suite checks it against the in-memory reference.
"""

from __future__ import annotations

HISTORY_SQL = """
SELECT hour, open_avg
FROM open_hourly(%(building)s, %(since)s, %(until)s, %(offline)s)
ORDER BY hour
"""


def policy_statements(retention_days: int, offline_s: int) -> list[str]:
    """Compression after a day, raw retention, and the hourly rollup job (D32, Q12)."""
    if retention_days <= 0 or offline_s <= 0:
        raise ValueError("retention_days and offline_s must be positive")
    return [
        """ALTER TABLE seat_readings SET (
             timescaledb.compress,
             timescaledb.compress_segmentby = 'seat_id',
             timescaledb.compress_orderby = 'time DESC')""",
        "SELECT add_compression_policy('seat_readings', INTERVAL '1 day', if_not_exists => true)",
        "SELECT remove_retention_policy('seat_readings', if_exists => true)",
        f"SELECT add_retention_policy('seat_readings', INTERVAL '{int(retention_days)} days')",
        "SELECT delete_job(job_id) FROM timescaledb_information.jobs"
        " WHERE proc_name = 'rollup_open_hourly'",
        "SELECT add_job('rollup_open_hourly', INTERVAL '1 hour',"
        f" config => '{{\"offline_s\": {int(offline_s)}}}'::jsonb)",
    ]
