"""Everything a service needs, injected once at startup."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from app.domain.types import Timers
from app.services.ports import Clock, Metrics, Notifier, NullMetrics, Repository, TopicAI


@dataclass(frozen=True)
class Context:
    repo: Repository
    ai: TopicAI
    notifier: Notifier
    clock: Clock
    timers: Timers
    map_cache_s: float
    history_window_h: int
    push_max_attempts: int
    vapid_public_key: str
    demo_hosts: bool = False  # D56
    demo_accept: timedelta = timedelta(seconds=5)
    search_stall: timedelta = timedelta(seconds=10)  # D61
    # The live stream (D61). The heartbeat is POLL_WEB_S, so a healthy stream stays "Live".
    live_enabled: bool = True
    live_check_s: float = 1.0
    live_ping_s: float = 3.0
    live_retry_s: float = 2.0
    live_stall_s: float = 30.0
    metrics: Metrics = field(default_factory=NullMetrics)  # D60
