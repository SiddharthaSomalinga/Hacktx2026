"""Builds the real adapters from Settings. Tests build their own Context instead."""

from __future__ import annotations

import logging

from app.adapters.ai_fallback import FallbackAI
from app.adapters.clock import SystemClock
from app.adapters.push_webpush import WebPushNotifier
from app.adapters.repo_postgres import PostgresRepository
from app.config import Settings
from app.services.container import Services
from app.services.context import Context
from app.services.ports import TopicAI

log = logging.getLogger("ghostseats.wiring")


def build_ai(settings: Settings) -> TopicAI:
    # The Muse Spark adapter is added once API access and docs exist (U1). Until then every
    # AI call uses the deterministic fallback, which NFR-3 requires to be complete anyway.
    if settings.muse_api_key is not None:
        log.warning(
            "MUSE_API_KEY is set but the Muse adapter is not built yet (U1); using fallback"
        )
    return FallbackAI()


def build_services(settings: Settings) -> Services:
    repo = PostgresRepository(
        settings.database_url, settings.database_read_url, pool_size=settings.db_pool_size
    )
    ctx = Context(
        repo=repo,
        ai=build_ai(settings),
        notifier=WebPushNotifier(
            settings.vapid_private_key.get_secret_value(), settings.vapid_subject
        ),
        clock=SystemClock(),
        timers=settings.timers(),
        map_cache_s=settings.map_cache_s,
        history_window_h=settings.history_window_h,
        push_max_attempts=settings.push_max_attempts,
        vapid_public_key=settings.vapid_public_key,
    )
    return Services.build(ctx)
