"""Postgres test support: a disposable database at TEST_DATABASE_URL, reset between tests."""

from __future__ import annotations

import os
from pathlib import Path

import psycopg

SCHEMA = Path(__file__).resolve().parents[1] / "sql" / "schema.sql"

TABLES = (
    "notification_outbox, push_subscriptions, reports, blocks, matches, requests, searches,"
    " host_sessions, topic_cache, users, seat_readings, seat_state, seats, nodes, tables, buildings"
)

WORLD_SQL = """
INSERT INTO buildings (id, name, is_simulated, busyness, lat, lng) VALUES
  ('lib', 'Library', false, 0, 30.2827, -97.7381),
  ('sim', 'Sim Hall', true, 0, 30.2866, -97.7376);
INSERT INTO tables (id, building_id, floor, label, x, y) VALUES
  ('t1', 'lib', 1, 'Table 01', 20, 20),
  ('t2', 'lib', 1, 'Table 02', 80, 20),
  ('x1', 'sim', 2, 'Table 01', 50, 50);
INSERT INTO nodes (id) VALUES ('n1');
INSERT INTO seats (id, table_id, node_id, position, is_simulated)
  SELECT 's' || p, 't1', 'n1', p, false FROM generate_series(1, 4) p;
INSERT INTO seat_state (seat_id, state, candidate_state)
  SELECT id, 'open', 'open' FROM seats WHERE NOT is_simulated;
INSERT INTO seats (id, table_id, node_id, position, is_simulated)
  SELECT 't2-s' || p, 't2', NULL, p, true FROM generate_series(1, 6) p;
INSERT INTO seats (id, table_id, node_id, position, is_simulated)
  SELECT 'x1-s' || p, 'x1', NULL, p, true FROM generate_series(1, 4) p;
INSERT INTO users (id, first_name, is_demo) VALUES
  ('alex', 'Alex', true), ('priya', 'Priya', true), ('jordan', 'Jordan', true),
  ('sam', 'Sam', true), ('simhost', 'Taylor', false);
"""


def test_database_url() -> str | None:
    return os.environ.get("TEST_DATABASE_URL")


_schema_applied = False


def reset(url: str) -> None:
    """Schema once per run, then an empty world for each test."""
    global _schema_applied
    with psycopg.connect(url, autocommit=True) as conn:
        if not _schema_applied:
            conn.execute(SCHEMA.read_text().encode())
            _schema_applied = True
        conn.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE".encode())
        conn.execute(WORLD_SQL.encode())
