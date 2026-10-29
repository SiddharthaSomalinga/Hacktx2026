"""Background loop in every instance: the scheduler tick, the outbox sender (D29, D30) and the
live sweep (D61).

Running one per instance is safe: the tick and the sender claim rows with SKIP LOCKED, and a
sweep only sends hints, which every instance may send. An error in one step is logged and the
loop carries on; the next round retries whatever is still due.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timedelta

from app.services.container import Services

log = logging.getLogger("ghostseats.worker")


class Worker:
    def __init__(self, services: Services, tick_s: float) -> None:
        self._services = services
        self._tick_s = tick_s
        self._stop = threading.Event()
        # Where the last sweep ended. Derived: after a restart the first sweep looks back one tick.
        self._swept_until: datetime | None = None
        self._thread = threading.Thread(target=self._run, name="ghostseats-worker", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 10.0) -> None:
        self._stop.set()
        self._thread.join(timeout)

    def run_once(self) -> None:
        try:
            self._services.scheduler.tick()
        except Exception:
            log.exception("scheduler tick failed")
        try:
            self._services.push.drain()
        except Exception:
            log.exception("outbox drain failed")
        until = self._services.ctx.clock.now()
        since = self._swept_until or until - timedelta(seconds=self._tick_s)
        try:
            self._services.scheduler.sweep(since, until)
            self._swept_until = until
        except Exception:
            log.exception("live sweep failed")  # the next sweep covers this window too

    def _run(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(self._tick_s)
