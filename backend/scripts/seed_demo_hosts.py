"""Seat one simulated host for every course in the catalog (FR-48, D56).

uv run python -m scripts.seed_demo_hosts

Any topic a student types then finds someone studying it. Hosts sit on simulated seats, spread
round-robin across the simulated tables, and never expire. Idempotent: ids are derived from the
course code, so running it again changes nothing. With DEMO_HOSTS on they also accept requests.
"""

from __future__ import annotations

import uuid

import psycopg

from app.domain.catalog import COURSES
from app.domain.topic_rules import label_for
from scripts.db import _url

NAMES = [
    "Taylor", "Riley", "Avery", "Morgan", "Jamie", "Casey", "Quinn", "Rowan", "Sage", "Emerson",
    "Hayden", "Parker", "Reese", "Dakota", "Skyler", "Finley", "Kendall", "Logan", "Marley",
    "Nico", "Peyton", "Remy", "Shay", "Tatum",
]  # fmt: skip

MAJORS = {
    "chemistry": "Chemistry",
    "mathematics": "Mathematics",
    "computer science": "Computer Science",
    "physics": "Physics",
    "biology": "Biology",
    "economics": "Economics",
    "statistics": "Statistics",
    "psychology": "Psychology",
}

NAMESPACE = uuid.UUID("5b1c2d1e-8f0a-4c1e-9a77-6d0e2f3b4a10")


def main() -> None:
    with psycopg.connect(_url(), autocommit=True) as conn:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT s.table_id FROM seats s WHERE s.is_simulated ORDER BY 1"
            ).fetchall()
        ]
        taken = {
            r[0]
            for r in conn.execute(
                "SELECT seat_id FROM host_sessions WHERE ended_at IS NULL"
            ).fetchall()
        }
        added = 0
        for i, course in enumerate(sorted(COURSES.values(), key=lambda c: c.code)):
            session_id = uuid.uuid5(NAMESPACE, course.code)
            user_id = f"sim-{course.code.lower().replace(' ', '')}"
            table = tables[i % len(tables)]
            seat = next(
                r[0]
                for r in conn.execute(
                    "SELECT id FROM seats WHERE table_id = %s ORDER BY position", (table,)
                ).fetchall()
                if r[0] not in taken
            )
            name = NAMES[i % len(NAMES)]
            conn.execute(
                "INSERT INTO users (id, first_name, major, is_demo) VALUES (%s, %s, %s, false)"
                " ON CONFLICT (id) DO NOTHING",
                (user_id, name, MAJORS.get(course.subject)),
            )
            row = conn.execute(
                """INSERT INTO host_sessions (id, user_id, seat_id, topic_raw, course_code, subject,
                       keywords, label, open, muted, started_at, expires_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true, false, now(),
                           '2100-01-01T00:00:00Z')
                   ON CONFLICT (id) DO NOTHING RETURNING id""",
                (
                    session_id,
                    user_id,
                    seat,
                    f"{course.code} study session",
                    course.code,
                    course.subject,
                    course.title.lower().split()[:3],
                    label_for(course, course.subject),
                ),
            ).fetchone()
            if row:
                taken.add(seat)
                added += 1
        print(f"{added} demo hosts added, {len(COURSES)} courses covered")


if __name__ == "__main__":
    main()
