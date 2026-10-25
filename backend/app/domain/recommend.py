"""Seat recommendation, widening from table to floor to building (FR-11, D21)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.domain.geometry import nearest_building, point_distance
from app.domain.types import Building, PublicState, RecommendLevel, Seat, SeatView, Table


@dataclass(frozen=True)
class Pick:
    seat: Seat
    kind: PublicState
    level: RecommendLevel


@dataclass(frozen=True)
class Full:
    nearest_building_id: str | None


@dataclass(frozen=True)
class Selection:
    building: Building
    floor: int | None
    table: Table | None


_PREFERENCE = (PublicState.OPEN, PublicState.LIKELY_OPENING)


def _key(sel: Selection) -> Callable[[Seat], tuple[int, float, int, str]]:
    """Nearest the selection: closest floor, then closest to the selected table, then lowest
    position, then seat id so the answer is deterministic."""

    def key(seat: Seat) -> tuple[int, float, int, str]:
        floor_gap = abs(seat.floor - sel.floor) if sel.floor is not None else 0
        near = point_distance(seat, sel.table.x, sel.table.y) if sel.table is not None else 0.0
        return (floor_gap, near, seat.position, seat.id)

    return key


def _best(views: list[SeatView], sel: Selection) -> tuple[Seat, PublicState] | None:
    """Open before likely-opening, then nearest the selection."""
    for kind in _PREFERENCE:
        matching = [v.seat for v in views if v.state is kind]
        if matching:
            return min(matching, key=_key(sel)), kind
    return None


def recommend(
    views: list[SeatView],
    sel: Selection,
    open_buildings: list[Building],
) -> Pick | Full:
    """`views` are every seat of `sel.building`; `open_buildings` are other buildings that
    currently have at least one open seat (for the full-building fallback)."""
    floor = sel.table.floor if sel.table is not None else sel.floor
    levels: list[tuple[RecommendLevel, list[SeatView]]] = []
    if sel.table is not None:
        levels.append((RecommendLevel.TABLE, [v for v in views if v.seat.table_id == sel.table.id]))
    if floor is not None:
        levels.append((RecommendLevel.FLOOR, [v for v in views if v.seat.floor == floor]))
    levels.append((RecommendLevel.BUILDING, views))

    effective = Selection(sel.building, floor, sel.table)
    for level, scope in levels:
        best = _best(scope, effective)
        if best is not None:
            seat, kind = best
            return Pick(seat, kind, level)
    nearest = nearest_building(sel.building, open_buildings)
    return Full(nearest.id if nearest else None)
