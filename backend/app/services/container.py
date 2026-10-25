"""All services, built once from a Context."""

from __future__ import annotations

from dataclasses import dataclass, replace

from app.services.ai_guard import GuardedAI
from app.services.auth import AuthService
from app.services.context import Context
from app.services.health import HealthService
from app.services.history import HistoryService
from app.services.host import HostService
from app.services.lifecycle import LifecycleService
from app.services.map import MapService
from app.services.match import MatchService
from app.services.push import PushService
from app.services.readings import ReadingsService
from app.services.requests import RequestService
from app.services.safety import SafetyService
from app.services.scheduler import SchedulerService
from app.services.search import SearchService
from app.services.topics import TopicsService


@dataclass(frozen=True)
class Services:
    ctx: Context
    lifecycle: LifecycleService
    health: HealthService
    readings: ReadingsService
    map: MapService
    history: HistoryService
    auth: AuthService
    host: HostService
    search: SearchService
    requests: RequestService
    match: MatchService
    safety: SafetyService
    push: PushService
    scheduler: SchedulerService

    @staticmethod
    def build(ctx: Context) -> Services:
        ctx = replace(ctx, ai=GuardedAI(ctx.ai))  # NFR-3 for every caller
        lifecycle = LifecycleService(ctx)
        topics = TopicsService(ctx)
        requests = RequestService(ctx, lifecycle)
        return Services(
            ctx=ctx,
            lifecycle=lifecycle,
            health=HealthService(ctx),
            readings=ReadingsService(ctx, lifecycle),
            map=MapService(ctx),
            history=HistoryService(ctx),
            auth=AuthService(ctx, lifecycle),
            host=HostService(ctx, lifecycle, topics),
            search=SearchService(ctx, lifecycle, topics),
            requests=requests,
            match=MatchService(ctx, lifecycle),
            safety=SafetyService(ctx),
            push=PushService(ctx),
            scheduler=SchedulerService(ctx, lifecycle, requests),
        )
