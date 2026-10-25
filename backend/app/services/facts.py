"""Read-side helper: seat states, table occupancy and host findability, loaded lazily per tx.

One `Facts` lives for one transaction, so every question in that transaction is answered from
the same snapshot and FR-24 is evaluated identically by every service.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from app.domain.matching import HostFacts, host_status
from app.domain.seat_engine import public_state
from app.domain.simulation import simulated_state
from app.domain.types import (
    Building,
    HiddenReason,
    HostSession,
    HostVisibility,
    PublicState,
    Seat,
    SeatState,
    SeatView,
    Table,
    Timers,
)
from app.services.ports import Tx


class Facts:
    def __init__(self, tx: Tx, now: datetime, t: Timers) -> None:
        self.tx = tx
        self.now = now
        self.t = t
        self._buildings: dict[str, Building] | None = None
        self._tables: dict[str, Table] = {}
        self._seats_by_building: dict[str, list[Seat]] = {}
        self._seats: dict[str, Seat] = {}
        self._states: dict[str, SeatState] = {}

    # --- places --------------------------------------------------------------

    def buildings(self) -> dict[str, Building]:
        if self._buildings is None:
            self._buildings = {b.id: b for b in self.tx.buildings()}
        return self._buildings

    def building(self, building_id: str) -> Building | None:
        return self.buildings().get(building_id)

    def _load_building(self, building_id: str) -> list[Seat]:
        if building_id not in self._seats_by_building:
            seats = self.tx.seats(building_id)
            for table in self.tx.tables(building_id):
                self._tables[table.id] = table
            real = [s.id for s in seats if not s.is_simulated]
            self._states.update(self.tx.seat_states(real))
            for s in seats:
                self._seats[s.id] = s
            self._seats_by_building[building_id] = seats
        return self._seats_by_building[building_id]

    def seats_of(self, building_id: str) -> list[Seat]:
        return self._load_building(building_id)

    def tables_of(self, building_id: str) -> list[Table]:
        self._load_building(building_id)
        return [t for t in self._tables.values() if t.building_id == building_id]

    def seat(self, seat_id: str) -> Seat | None:
        if seat_id not in self._seats:
            found = self.tx.seat(seat_id)
            if found is None:
                return None
            self._load_building(found.building_id)
        return self._seats.get(seat_id)

    def table(self, table_id: str) -> Table | None:
        return self._tables.get(table_id)

    def table_of(self, seat: Seat) -> Table:
        self._load_building(seat.building_id)
        return self._tables[seat.table_id]

    # --- states --------------------------------------------------------------

    def seat_state(self, seat: Seat) -> SeatState | None:
        self._load_building(seat.building_id)
        return self._states.get(seat.id)

    def state(self, seat: Seat) -> PublicState:
        if seat.is_simulated:
            busyness = self.buildings()[seat.building_id].busyness
            return simulated_state(seat.id, self.now, busyness, self.t)
        st = self.seat_state(seat)
        return public_state(st, self.now, self.t) if st else PublicState.OFFLINE

    def views(self, building_id: str) -> list[SeatView]:
        return [SeatView(s, self.state(s)) for s in self.seats_of(building_id)]

    def open_seats_at_table(self, seat: Seat) -> list[Seat]:
        return [
            s
            for s in self.seats_of(seat.building_id)
            if s.table_id == seat.table_id and self.state(s) is PublicState.OPEN
        ]

    def open_seats_on_floor(self, seat: Seat) -> list[Seat]:
        return [
            s
            for s in self.seats_of(seat.building_id)
            if s.floor == seat.floor and self.state(s) is PublicState.OPEN
        ]

    def counts(self, building_id: str) -> dict[PublicState, int]:
        out: dict[PublicState, int] = defaultdict(int)
        for s in self.seats_of(building_id):
            out[self.state(s)] += 1
        return out

    # --- hosts (FR-24) -------------------------------------------------------

    def host_facts(self, session: HostSession) -> HostFacts:
        seat = self.seat(session.seat_id)
        assert seat is not None, "host session references a missing seat"
        return HostFacts(
            session=session,
            seat=seat,
            seat_state=self.seat_state(seat),
            has_active_match=self.tx.active_match_for_session(session.id) is not None,
            table_open_seats=len(self.open_seats_at_table(seat)),
        )

    def host_status(
        self, session: HostSession | None
    ) -> tuple[HostVisibility, HiddenReason | None]:
        if session is None:
            return HostVisibility.ENDED, None
        return host_status(self.host_facts(session), self.now, self.t)
