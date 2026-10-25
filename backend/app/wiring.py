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


def _seed_demo_memory(repo: object) -> None:
    from app.domain.types import Building, Seat, SeatState, Table, User
    d = repo.data  # type: ignore[attr-defined]
    d.buildings["pcl"] = Building("pcl", "PCL Library", False, 45, 30.28270, -97.73810)
    d.buildings["wel"] = Building("wel", "WEL Library", True, 75, 30.28660, -97.73760)
    d.buildings["gdc"] = Building("gdc", "GDC Study Hall", True, 30, 30.28620, -97.73660)

    d.tables["pcl-2-t1"] = Table("pcl-2-t1", "pcl", 2, "Table 01", 25, 30)
    d.tables["pcl-2-t2"] = Table("pcl-2-t2", "pcl", 2, "Table 02", 60, 30)
    d.tables["wel-1-t1"] = Table("wel-1-t1", "wel", 1, "Table 01", 20, 30)
    d.tables["gdc-3-t1"] = Table("gdc-3-t1", "gdc", 3, "Table 01", 20, 35)

    d.nodes["table-1"] = None
    d.seats["t1-s1"] = Seat("t1-s1", "pcl-2-t1", "pcl", 2, 1, 25, 30, False, "table-1")
    d.seats["t1-s2"] = Seat("t1-s2", "pcl-2-t1", "pcl", 2, 2, 25, 30, False, "table-1")
    d.states["t1-s1"] = SeatState.never_seen("t1-s1")
    d.states["t1-s2"] = SeatState.never_seen("t1-s2")

    for p in range(1, 7):
        sid = f"pcl-2-t2-s{p}"
        d.seats[sid] = Seat(sid, "pcl-2-t2", "pcl", 2, p, 60, 30, True, None)
        sid_w = f"wel-1-t1-s{p}"
        d.seats[sid_w] = Seat(sid_w, "wel-1-t1", "wel", 1, p, 20, 30, True, None)
        sid_g = f"gdc-3-t1-s{p}"
        d.seats[sid_g] = Seat(sid_g, "gdc-3-t1", "gdc", 3, p, 20, 35, True, None)

    for uid, name in [
        ("u-alex", "Alex"),
        ("u-priya", "Priya"),
        ("u-jordan", "Jordan"),
        ("u-mateo", "Mateo"),
        ("u-sam", "Sam"),
        ("u-wei", "Wei"),
    ]:
        d.users[uid] = User(uid, name, True)


def build_services(settings: Settings) -> Services:
    if settings.database_url in ("memory", "memory://"):
        from tests.fakes import InMemoryRepository
        repo = InMemoryRepository()
        _seed_demo_memory(repo)
    else:
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
