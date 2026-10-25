"""All services, built once from a Context."""

from __future__ import annotations

from dataclasses import dataclass

from app.services.auth import AuthService
from app.services.context import Context
from app.services.health import HealthService
from app.services.history import HistoryService
from app.services.host import HostService
from app.services.map import MapService
from app.services.match import MatchService
from app.services.push import PushService
from app.services.readings import ReadingsService
from app.services.requests import RequestService
from app.services.safety import SafetyService
from app.services.scheduler import SchedulerService
from app.services.search import SearchService


@dataclass(frozen=True)
class Services:
    ctx: Context
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
        return Services(
            ctx=ctx,
            health=HealthService(ctx),
            readings=ReadingsService(ctx),
            map=MapService(ctx),
            history=HistoryService(ctx),
            auth=AuthService(ctx),
            host=HostService(ctx),
            search=SearchService(ctx),
            requests=RequestService(ctx),
            match=MatchService(ctx),
            safety=SafetyService(ctx),
            push=PushService(ctx),
            scheduler=SchedulerService(ctx),
        )
