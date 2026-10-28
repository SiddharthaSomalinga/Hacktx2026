"""Push subscriptions and the outbox sender (FR-51..53, D30).

The sender claims unsent outbox rows with SKIP LOCKED, so any number of instances can drain
concurrently without sending a row twice. A push failure never touches the transition that
produced the row: that was committed long before.
"""

from __future__ import annotations

import logging

from app.services.context import Context
from app.services.ports import PushOutcome, PushResult

log = logging.getLogger("ghostseats.push")


class PushService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def vapid_public_key(self) -> str:
        return self._ctx.vapid_public_key

    def subscribe(self, user_id: str, endpoint: str, p256dh: str, auth: str) -> None:
        now = self._ctx.clock.now()
        with self._ctx.repo.tx() as tx:
            tx.upsert_subscription(user_id, endpoint, p256dh, auth, now)

    def unsubscribe(self, user_id: str, endpoint: str) -> None:
        with self._ctx.repo.tx() as tx:
            tx.delete_subscription(endpoint, user_id)

    def drain(self, limit: int = 50) -> int:
        """Send up to `limit` unsent notifications. Returns how many rows were finished."""
        finished = 0
        with self._ctx.repo.tx() as tx:
            for row in tx.claim_outbox(limit):
                failed = False
                for sub in tx.subscriptions_for(row.message.user_id):
                    result = self._ctx.notifier.send(sub, row.message.payload)
                    if result is PushResult.GONE:
                        tx.delete_subscription(sub.endpoint)
                    elif result is PushResult.FAILED:
                        failed = True
                attempts = row.attempts + 1
                if failed and attempts < self._ctx.push_max_attempts:
                    tx.mark_outbox(row.id, None, attempts)  # retried on a later tick
                    self._ctx.metrics.count_push(PushOutcome.RETRY)
                    continue
                if failed:
                    log.warning("giving up on outbox row %d after %d attempts", row.id, attempts)
                tx.mark_outbox(row.id, self._ctx.clock.now(), attempts)
                self._ctx.metrics.count_push(PushOutcome.GAVE_UP if failed else PushOutcome.SENT)
                finished += 1
        return finished
