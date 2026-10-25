from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.adapters.ai_fallback import FallbackAI
from app.config import Settings
from app.main import create_app
from app.services.container import Services
from app.services.context import Context
from tests.fakes import FakeClock, FakeNotifier, InMemoryRepository

NODE_KEY = "test-node-key-0123456789"


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "database_url": "postgresql://unused",
        "secret_key": "s" * 32,
        "node_key": NODE_KEY,
        "vapid_public_key": "test-public-key",
        "vapid_private_key": "test-private-key",
        "vapid_subject": "mailto:team@example.com",
        "worker_enabled": False,
        "debounce_s": 0,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[arg-type, call-arg]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def repo() -> InMemoryRepository:
    return InMemoryRepository()


@pytest.fixture
def settings() -> Settings:
    return make_settings()


@pytest.fixture
def services(
    repo: InMemoryRepository, clock: FakeClock, notifier: FakeNotifier, settings: Settings
) -> Services:
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
    )
    return Services.build(ctx)


@pytest.fixture
def client(settings: Settings, services: Services) -> Iterator[TestClient]:
    with TestClient(create_app(settings, services)) as test_client:
        yield test_client
