"""`Metrics` over prometheus_client (D60).

The image runs several uvicorn processes per container, and a scrape reaches only one of them.
With PROMETHEUS_MULTIPROC_DIR set (before prometheus_client is first imported, which the
environment guarantees), every process writes its samples to files in that directory, and
`render` sums the files of all processes. Without it, as in `make dev`, the process's own
registry is the whole story.
"""

from __future__ import annotations

from collections.abc import Iterator

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Histogram,
    generate_latest,
)
from prometheus_client.core import GaugeMetricFamily, Metric
from prometheus_client.multiprocess import MultiProcessCollector
from prometheus_client.registry import Collector

from app.services.ports import PushOutcome


class PrometheusMetrics:
    def __init__(self, multiprocess_dir: str | None) -> None:
        self._multiprocess_dir = multiprocess_dir
        self._registry = CollectorRegistry()
        r = self._registry
        self._requests = Histogram(
            "ghostseats_http_request_duration_seconds",
            "Time to answer a request, by route template and status",
            ["method", "route", "status"],
            registry=r,
        )
        self._tick = Histogram(
            "ghostseats_scheduler_tick_duration_seconds",
            "Time for one scheduler tick, including the rows it advanced",
            registry=r,
        )
        self._due = Counter(
            "ghostseats_scheduler_due_rows",
            "Due sessions, matches and searches the ticks found, plus demo accepts",
            registry=r,
        )
        self._push = Counter(
            "ghostseats_push_notifications",
            "Outbox rows handled by the sender, by outcome",
            ["outcome"],
            registry=r,
        )
        self._ai_fallbacks = Counter(
            "ghostseats_ai_fallbacks",
            "AI calls answered by the deterministic fallback after a failure",
            ["call"],
            registry=r,
        )

    def observe_request(self, method: str, route: str, status: int, seconds: float) -> None:
        self._requests.labels(method, route, str(status)).observe(seconds)

    def observe_tick(self, seconds: float, due: int) -> None:
        self._tick.observe(seconds)
        self._due.inc(due)

    def count_push(self, outcome: PushOutcome) -> None:
        self._push.labels(outcome.value).inc()

    def count_ai_fallback(self, call: str) -> None:
        self._ai_fallbacks.labels(call).inc()

    def render(self, outbox_unsent: int) -> tuple[bytes, str]:
        if self._multiprocess_dir is None:
            recorded = self._registry
        else:
            recorded = CollectorRegistry()
            # The library leaves this constructor unannotated.
            MultiProcessCollector(recorded, path=self._multiprocess_dir)  # type: ignore[no-untyped-call]
        live = CollectorRegistry()
        live.register(_OutboxBacklog(outbox_unsent))
        return generate_latest(recorded) + generate_latest(live), CONTENT_TYPE_LATEST


class _OutboxBacklog(Collector):
    """Read from the database at scrape time. A Gauge object would be written to the
    multiprocess files and summed across processes; this value is already the total."""

    def __init__(self, unsent: int) -> None:
        self._unsent = unsent

    def collect(self) -> Iterator[Metric]:
        yield GaugeMetricFamily(
            "ghostseats_outbox_unsent", "Notifications not yet sent", value=self._unsent
        )
