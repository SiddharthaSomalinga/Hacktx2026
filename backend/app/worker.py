"""Background loop in every instance: the scheduler tick and the outbox sender (D29, D30).

Running one per instance is safe: both claim rows with SKIP LOCKED. An error in one tick is
logged and the loop carries on; the next tick retries whatever is still due.
"""

from __future__ import annotations

import logging
import threading

from app.services.container import Services

log = logging.getLogger("ghostseats.worker")


class Worker:
    def __init__(self, services: Services, tick_s: float) -> None:
        self._services = services
        self._tick_s = tick_s
        self._stop = threading.Event()
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

    def _run(self) -> None:
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(self._tick_s)
