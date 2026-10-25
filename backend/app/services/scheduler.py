"""The scheduler tick (NFR-2, D29): advances rows whose deadline passed with nobody polling.

Each row is advanced in its own transaction with SKIP LOCKED, so ticks on several instances
split the work instead of queueing behind each other.
"""

from __future__ import annotations

import logging

from app.services.context import Context
from app.services.lifecycle import LifecycleService
from app.services.ports import Lock

log = logging.getLogger("ghostseats.scheduler")


class SchedulerService:
    def __init__(self, ctx: Context, lifecycle: LifecycleService) -> None:
        self._ctx = ctx
        self._lifecycle = lifecycle

    def tick(self) -> int:
        now = self._ctx.clock.now()
        t = self._ctx.timers
        with self._ctx.repo.read() as tx:
            sessions = tx.due_session_ids(now, now - t.host_end)
            matches = tx.due_match_ids(now, now - t.host_leave_cancel)
            searches = tx.due_search_ids(now, now - t.human_fresh)
        for session_id in sessions:
            self._lifecycle.advance_session(session_id, Lock.SKIP)
        for match_id in matches:
            self._lifecycle.advance_match(match_id, Lock.SKIP)
        for search_id in searches:
            self._lifecycle.advance_search(search_id, Lock.SKIP)
        return len(sessions) + len(matches) + len(searches)
