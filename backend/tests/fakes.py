"""Test doubles for the ports: controllable clock, recording notifier, in-memory repository."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from app.services.ports import PushResult, PushSubscription

T0 = datetime(2026, 10, 24, 18, 0, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, start: datetime = T0) -> None:
        self._now = start
        self._mono = 1000.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._mono

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
        self._mono += seconds


class FakeNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, str]]] = []
        self.results: dict[str, PushResult] = {}

    def send(self, subscription: PushSubscription, payload: Mapping[str, str]) -> PushResult:
        result = self.results.get(subscription.endpoint, PushResult.SENT)
        if result is PushResult.SENT:
            self.sent.append((subscription.endpoint, dict(payload)))
        return result


class InMemoryRepository:
    """Grows into the full in-memory Repository in B1."""

    def ping(self) -> bool:
        return True
