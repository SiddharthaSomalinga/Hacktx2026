"""Occupancy history (FR-49, D31): hourly average open seats over HISTORY_WINDOW_H."""

from __future__ import annotations

from datetime import datetime, timedelta

from app.services.context import Context
from app.services.errors import not_found


def hour_floor(t: datetime) -> datetime:
    return t.replace(minute=0, second=0, microsecond=0)


class HistoryService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def window(self) -> tuple[datetime, datetime]:
        now = self._ctx.clock.now()
        since = hour_floor(now) - timedelta(hours=self._ctx.history_window_h - 1)
        return since, now

    def history(self, building_id: str) -> list[tuple[datetime, float]]:
        with self._ctx.repo.read() as tx:
            if building_id not in {b.id for b in tx.buildings()}:
                raise not_found("building_not_found", f"No building {building_id!r}")
        since, until = self.window()
        return self._ctx.repo.history(building_id, since, until, self._ctx.timers.offline)
