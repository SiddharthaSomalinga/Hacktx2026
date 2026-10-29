from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta

import pytest
from fastapi import FastAPI

from app.config import Settings
from app.main import create_app
from app.services.container import Services
from tests.api.harness import Node, Phone
from tests.conftest import make_settings
from tests.fakes import FakeClock, FakeNotifier, InMemoryRepository
from tests.world import build_world


@dataclass
class World:
    app: FastAPI
    services: Services
    repo: InMemoryRepository
    clock: FakeClock
    notifier: FakeNotifier
    node: Node

    def phone(self, user_id: str | None = None) -> Phone:
        return Phone(self.app, user_id)


@pytest.fixture
def settings() -> Settings:
    # Map caching is exercised by its own tests; flows read fresh state.
    return make_settings(map_cache_s=0)


@pytest.fixture
def world(
    settings: Settings,
    services: Services,
    repo: InMemoryRepository,
    clock: FakeClock,
    notifier: FakeNotifier,
) -> World:
    build_world(repo)
    app = create_app(settings, services)
    return World(app, services, repo, clock, notifier, Node(app, clock))


@pytest.fixture
def make_world(
    repo: InMemoryRepository, clock: FakeClock, notifier: FakeNotifier
) -> Callable[..., World]:
    """For tests that need non-default settings (e.g. map caching)."""
    from app.adapters.ai_fallback import FallbackAI
    from app.services.context import Context

    def make(**overrides: object) -> World:
        settings = make_settings(**overrides)
        ctx = Context(
            repo=repo,  # type: ignore[arg-type]
            ai=FallbackAI(),
            notifier=notifier,
            clock=clock,
            timers=settings.timers(),
            map_cache_s=settings.map_cache_s,
            history_window_h=settings.history_window_h,
            push_max_attempts=settings.push_max_attempts,
            vapid_public_key=settings.vapid_public_key,
            demo_hosts=settings.demo_hosts,
            demo_accept=timedelta(seconds=settings.demo_accept_s),
            search_stall=timedelta(seconds=settings.search_stall_s),
        )
        services = Services.build(ctx)
        build_world(repo)
        app = create_app(settings, services)
        return World(app, services, repo, clock, notifier, Node(app, clock))

    return make
