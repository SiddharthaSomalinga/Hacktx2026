"""A small, fully controlled world for service and API tests.

    Building "lib" (real, lat/lng set), floor 1:
      table "t1" at (20, 20): real seats s1..s4 on node "n1"
      table "t2" at (80, 20): simulated seats t2-s1..t2-s6
    Building "sim" (simulated, busyness 0 → every seat open): table "x1", seats x1-s1..x1-s4

Users: alex, priya, jordan, sam (demo) and simhost (seeded simulated host, not a demo user).
"""

from __future__ import annotations

from app.domain.types import Building, Seat, SeatState, Table, User
from tests.fakes import InMemoryRepository

NODE = "n1"
REAL_SEATS = ["s1", "s2", "s3", "s4"]
USERS = ["alex", "priya", "jordan", "sam"]
MAJORS = {"alex": "Biochemistry", "priya": "Chemistry", "jordan": "Computer Science"}


def build_world(repo: InMemoryRepository, *, lib_busyness: int = 0) -> None:
    d = repo.data
    d.buildings["lib"] = Building("lib", "Library", False, lib_busyness, 30.2827, -97.7381)
    d.buildings["sim"] = Building("sim", "Sim Hall", True, 0, 30.2866, -97.7376)
    for t in (
        Table("t1", "lib", 1, "Table 01", 20, 20),
        Table("t2", "lib", 1, "Table 02", 80, 20),
        Table("x1", "sim", 2, "Table 01", 50, 50),
    ):
        d.tables[t.id] = t
    for i, sid in enumerate(REAL_SEATS, start=1):
        d.seats[sid] = Seat(sid, "t1", "lib", 1, i, 20, 20, False, NODE)
        d.states[sid] = SeatState.never_seen(sid)
    for i in range(1, 7):
        d.seats[f"t2-s{i}"] = Seat(f"t2-s{i}", "t2", "lib", 1, i, 80, 20, True, None)
    for i in range(1, 5):
        d.seats[f"x1-s{i}"] = Seat(f"x1-s{i}", "x1", "sim", 2, i, 50, 50, True, None)
    d.nodes[NODE] = None
    for name in USERS:
        d.users[name] = User(name, name.title(), True, MAJORS.get(name))
    d.users["simhost"] = User("simhost", "Taylor", False)
