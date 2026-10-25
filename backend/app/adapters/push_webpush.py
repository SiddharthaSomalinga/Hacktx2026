"""Web push over VAPID (FR-51..53). Endpoints are never logged: they identify a device."""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping

from pywebpush import WebPushException, webpush

from app.services.ports import PushResult, PushSubscription

log = logging.getLogger("ghostseats.push")

_TTL_S = 300  # a request or match notice is useless after a few minutes


class WebPushNotifier:
    def __init__(self, private_key: str, subject: str, timeout_s: float = 5.0) -> None:
        self._private_key = private_key
        self._claims = {"sub": subject}
        self._timeout_s = timeout_s

    def send(self, subscription: PushSubscription, payload: Mapping[str, str]) -> PushResult:
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=json.dumps(dict(payload)),
                vapid_private_key=self._private_key,
                vapid_claims=dict(self._claims),
                ttl=_TTL_S,
                timeout=self._timeout_s,
            )
            return PushResult.SENT
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in (404, 410):
                return PushResult.GONE
            log.warning("push failed with status %s", status)
            return PushResult.FAILED
        except Exception as exc:  # network errors from requests: retried by the outbox
            log.warning("push failed: %s", type(exc).__name__)
            return PushResult.FAILED
