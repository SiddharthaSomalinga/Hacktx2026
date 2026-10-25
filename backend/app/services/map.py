"""Seat map snapshots and recommendations (FR-8..13, D21, D32).

Snapshots are derived data, cached in memory for MAP_CACHE_S per instance (NFR-8). The ETag is
a hash of the exact bytes served, so a 304 is only ever sent for identical content.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections import defaultdict
from collections.abc import Callable

from app.domain.recommend import Full, Selection, recommend
from app.domain.types import PublicState
from app.services.context import Context
from app.services.errors import not_found
from app.services.facts import Facts
from app.services.views import BuildingFullView, Cached, RecommendationView, SeatLookupView


def to_cached(body: object) -> Cached:
    content = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode()
    return Cached(content, f'"{hashlib.sha256(content).hexdigest()[:32]}"')


class MapService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx
        self._cache: dict[str, tuple[float, Cached]] = {}
        self._lock = threading.Lock()

    def _cached(self, key: str, build: Callable[[], Cached]) -> Cached:
        ttl = self._ctx.map_cache_s
        now = self._ctx.clock.monotonic()
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None and hit[0] > now:
                return hit[1]
        value = build()
        if ttl > 0:
            with self._lock:
                self._cache[key] = (now + ttl, value)
        return value

    def summaries(self) -> list[dict[str, object]]:
        now = self._ctx.clock.now()
        with self._ctx.repo.read() as tx:
            facts = Facts(tx, now, self._ctx.timers)
            out: list[dict[str, object]] = []
            for b in sorted(facts.buildings().values(), key=lambda b: b.name):
                counts = facts.counts(b.id)
                out.append(
                    {
                        "id": b.id,
                        "name": b.name,
                        "is_simulated": b.is_simulated,
                        "open": counts[PublicState.OPEN],
                        "likely_opening": counts[PublicState.LIKELY_OPENING],
                        "occupied": counts[PublicState.OCCUPIED],
                        "offline": counts[PublicState.OFFLINE],
                        "total": sum(counts.values()),
                    }
                )
        return out

    def buildings(self) -> Cached:
        return self._cached("buildings", lambda: to_cached(self.summaries()))

    def _detail(self, building_id: str) -> Cached:
        now = self._ctx.clock.now()
        with self._ctx.repo.read() as tx:
            facts = Facts(tx, now, self._ctx.timers)
            b = facts.building(building_id)
            if b is None:
                raise not_found("building_not_found", f"No building {building_id!r}")
            by_table: dict[str, list[dict[str, object]]] = defaultdict(list)
            for v in sorted(facts.views(building_id), key=lambda v: v.seat.position):
                by_table[v.seat.table_id].append(
                    {"id": v.seat.id, "position": v.seat.position, "state": v.state.value}
                )
            floors: dict[int, list[dict[str, object]]] = defaultdict(list)
            for t in sorted(facts.tables_of(building_id), key=lambda t: (t.floor, t.label)):
                floors[t.floor].append(
                    {"id": t.id, "label": t.label, "x": t.x, "y": t.y, "seats": by_table[t.id]}
                )
        return to_cached(
            {
                "id": b.id,
                "name": b.name,
                "is_simulated": b.is_simulated,
                "floors": [{"floor": f, "tables": floors[f]} for f in sorted(floors)],
            }
        )

    def building(self, building_id: str) -> Cached:
        return self._cached(f"building:{building_id}", lambda: self._detail(building_id))

    def recommend(
        self, building_id: str, floor: int | None, table_id: str | None
    ) -> RecommendationView | BuildingFullView:
        now = self._ctx.clock.now()
        with self._ctx.repo.read() as tx:
            facts = Facts(tx, now, self._ctx.timers)
            b = facts.building(building_id)
            if b is None:
                raise not_found("building_not_found", f"No building {building_id!r}")
            views = facts.views(building_id)
            table = None
            if table_id is not None:
                table = facts.table(table_id)
                if table is None or table.building_id != building_id:
                    raise not_found("table_not_found", f"No table {table_id!r} in {building_id!r}")
            open_elsewhere = [
                other
                for other in facts.buildings().values()
                if other.id != building_id and facts.counts(other.id)[PublicState.OPEN] > 0
            ]
        result = recommend(views, Selection(b, floor, table), open_elsewhere)
        if isinstance(result, Full):
            return BuildingFullView(result.nearest_building_id)
        return RecommendationView(
            seat_id=result.seat.id,
            table_id=result.seat.table_id,
            floor=result.seat.floor,
            kind=result.kind,
            level=result.level,
        )

    def seat(self, seat_id: str) -> SeatLookupView:
        """Where a seat is and its public state (D53), for seat links and QR codes."""
        now = self._ctx.clock.now()
        with self._ctx.repo.read() as tx:
            facts = Facts(tx, now, self._ctx.timers)
            seat = facts.seat(seat_id)
            if seat is None:
                raise not_found("seat_not_found", f"No seat {seat_id!r}")
            return SeatLookupView(
                id=seat.id,
                building_id=seat.building_id,
                floor=seat.floor,
                table_id=seat.table_id,
                table_label=facts.table_of(seat).label,
                position=seat.position,
                state=facts.state(seat),
            )
