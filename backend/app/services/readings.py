"""Sensor ingest (FR-1..7, D29, D31)."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.types import Led, Reading
from app.services.context import Context


class ReadingsService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def ingest(self, node_id: str, readings: Sequence[Reading]) -> dict[str, Led]:
        raise NotImplementedError
