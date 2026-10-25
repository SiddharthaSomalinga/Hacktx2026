"""The scheduler tick for time-only deadlines (NFR-2, D29)."""

from __future__ import annotations

from app.services.context import Context


class SchedulerService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def tick(self) -> int:
        raise NotImplementedError
