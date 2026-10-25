"""Distances between seats and buildings (FR-11, FR-37, FR-39).

Seats are placed by their table's (x, y) on the floor canvas plus their position at the table.
Two seats at the same table are ordered by how far apart their positions are; seats at
different tables by the distance between the tables.
"""

from __future__ import annotations

import math

from app.domain.types import Building, Seat


def seat_distance(a: Seat, b: Seat) -> tuple[float, int]:
    """Sort key: table distance on the canvas first, then position difference."""
    return (math.hypot(a.x - b.x, a.y - b.y), abs(a.position - b.position))


def point_distance(seat: Seat, x: float, y: float) -> float:
    return math.hypot(seat.x - x, seat.y - y)


def haversine_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def nearest_seat(origin: Seat, candidates: list[Seat]) -> Seat | None:
    """The candidate closest to `origin` (excluding itself); ties broken by seat id."""
    others = [c for c in candidates if c.id != origin.id]
    if not others:
        return None
    return min(others, key=lambda c: (seat_distance(origin, c), c.id))


def nearest_building(origin: Building, candidates: list[Building]) -> Building | None:
    if origin.lat is None or origin.lng is None:
        return None
    lat, lng = origin.lat, origin.lng
    located = [
        b for b in candidates if b.id != origin.id and b.lat is not None and b.lng is not None
    ]
    if not located:
        return None
    return min(located, key=lambda b: (haversine_km(lat, lng, b.lat, b.lng), b.id))  # type: ignore[arg-type]
