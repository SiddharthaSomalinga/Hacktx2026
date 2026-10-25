"""Builds the real adapters from Settings. Tests build their own Context instead."""

from __future__ import annotations

import logging

from app.adapters.ai_fallback import FallbackAI
from app.adapters.ai_muse import MuseAI
from app.adapters.clock import SystemClock
from app.adapters.push_webpush import WebPushNotifier
from app.adapters.repo_postgres import PostgresRepository
from app.config import Settings
from app.services.container import Services
from app.services.context import Context
from app.services.ports import TopicAI

log = logging.getLogger("ghostseats.wiring")


def build_ai(settings: Settings) -> TopicAI:
    """Muse Spark when a key is set (D38), else the deterministic fallback (NFR-3)."""
    if settings.muse_api_key is None:
        log.info("MUSE_API_KEY not set; AI calls use the fallback")
        return FallbackAI()
    log.info("AI calls use %s at %s", settings.muse_model, settings.muse_base_url)
    return MuseAI(
        settings.muse_api_key.get_secret_value(),
        settings.muse_base_url,
        settings.muse_model,
        settings.ai_timeout_s,
    )


def build_services(settings: Settings) -> Services:
    repo = PostgresRepository(
        settings.database_url,
        settings.database_read_url,
        pool_size=settings.db_pool_size,
        timeout_s=settings.db_timeout_s,
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
