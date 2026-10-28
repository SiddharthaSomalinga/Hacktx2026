"""The scheduler tick (NFR-2, D29): advances rows whose deadline passed with nobody polling.

Each row is advanced in its own transaction with SKIP LOCKED, so ticks on several instances
split the work instead of queueing behind each other.
"""

from __future__ import annotations

import logging
from datetime import datetime

from app.services.context import Context
from app.services.errors import DomainError
from app.services.lifecycle import LifecycleService
from app.services.ports import Lock
from app.services.requests import RequestService

log = logging.getLogger("ghostseats.scheduler")


class SchedulerService:
    def __init__(self, ctx: Context, lifecycle: LifecycleService, requests: RequestService) -> None:
        self._ctx = ctx
        self._lifecycle = lifecycle
        self._requests = requests
        # When this process first saw each idle search. Derived, not state of record: losing it
        # only delays a resume by SEARCH_STALL_S.
        self._idle_since: dict[str, datetime] = {}

    def tick(self) -> int:
        started = self._ctx.clock.monotonic()
        now = self._ctx.clock.now()
        t = self._ctx.timers
        with self._ctx.repo.read() as tx:
            sessions = tx.due_session_ids(now, now - t.host_end)
            matches = tx.due_match_ids(now, now - t.host_leave_cancel)
            searches = tx.due_search_ids(now, now - t.human_fresh)
            idle = tx.idle_search_ids()
        searches += self._stalled(idle, now)
        for session_id in sessions:
            self._lifecycle.advance_session(session_id, Lock.SKIP)
        for match_id in matches:
            self._lifecycle.advance_match(match_id, Lock.SKIP)
        for search_id in searches:
            self._lifecycle.advance_search(search_id, Lock.SKIP)
        accepted = self._accept_for_demo_hosts(now) if self._ctx.demo_hosts else 0
        due = len(sessions) + len(matches) + len(searches) + accepted
        self._ctx.metrics.observe_tick(self._ctx.clock.monotonic() - started, due)
        return due

    def _stalled(self, idle: list[str], now: datetime) -> list[str]:
        """Idle searches this process has seen idle for SEARCH_STALL_S (D61). An idle search is
        normally a send in flight (ranking can take AI_TIMEOUT_S); one idle longer lost its send
        to a failure, and nothing else would resume it once clients stop polling."""
        self._idle_since = {sid: self._idle_since.get(sid, now) for sid in idle}
        return [
            sid for sid, since in self._idle_since.items() if now - since >= self._ctx.search_stall
        ]

    def _accept_for_demo_hosts(self, now: datetime) -> int:
        """D56: a simulated host accepts a request DEMO_ACCEPT_S after it arrives, through the
        same accept path a person uses, so the match, seat and icebreaker are real."""
        with self._ctx.repo.read() as tx:
            due = []
            for request_id in tx.demo_request_ids(now - self._ctx.demo_accept):
                request = tx.request(request_id)
                session = tx.session(request.host_session_id) if request else None
                if session is not None:
                    due.append((session.user_id, request_id))
        accepted = 0
        for host_user_id, request_id in due:
            try:
                self._requests.accept(host_user_id, request_id)
                accepted += 1
            except DomainError as exc:  # cancelled or expired meanwhile; nothing to accept
                log.info("demo accept skipped %s: %s", request_id, exc.code)
        return accepted
