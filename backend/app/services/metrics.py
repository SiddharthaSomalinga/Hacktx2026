"""What GET /metrics reports (D60): what the app recorded, plus the outbox backlog, read live."""

from __future__ import annotations

from app.services.context import Context


class MetricsService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def observe_request(self, method: str, route: str, status: int, seconds: float) -> None:
        self._ctx.metrics.observe_request(method, route, status, seconds)

    def render(self) -> tuple[bytes, str]:
        with self._ctx.repo.read() as tx:
            unsent = tx.outbox_unsent()
        return self._ctx.metrics.render(unsent)
