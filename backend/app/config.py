"""Every threshold and environment value (REQUIREMENTS §8, NFR-6), validated at startup."""

from __future__ import annotations

from datetime import timedelta
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.types import Timers


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", frozen=True)

    # Environment (required ones have no default, so a missing value stops startup).
    database_url: str
    database_read_url: str | None = None
    secret_key: SecretStr = Field(min_length=32)
    node_key: SecretStr = Field(min_length=16)
    vapid_public_key: str
    vapid_private_key: SecretStr
    vapid_subject: str = Field(pattern=r"^(mailto:|https://)")
    muse_api_key: SecretStr | None = None
    frontend_dist: str | None = None
    cookie_secure: bool = False
    worker_enabled: bool = True
    # Connections per pool per process. Budget: processes x instances x pools x this value must
    # stay under the database's max_connections (25 in the local Timescale image).
    db_pool_size: int = Field(5, gt=0, le=50)

    # Thresholds, seconds unless named otherwise.
    ghost_s: int = Field(30, gt=0)
    debounce_s: int = Field(5, ge=0)
    offline_s: int = Field(30, gt=0)
    human_fresh_s: int = Field(10, gt=0)
    request_timeout_s: int = Field(120, gt=0)
    max_hosts_per_search: int = Field(5, gt=0)
    host_end_s: int = Field(600, gt=0)
    host_leave_cancel_s: int = Field(120, gt=0)
    match_timeout_s: int = Field(1200, gt=0)
    blink_s: int = Field(60, gt=0)
    session_max_s: int = Field(10800, gt=0)
    confirm_grace_s: int = Field(120, gt=0)
    poll_web_s: int = Field(3, gt=0)
    ai_timeout_s: float = Field(4, gt=0)
    max_requests_per_hour: int = Field(10, gt=0)
    sim_slot_s: int = Field(60, gt=0)
    scheduler_tick_s: float = Field(2, gt=0)
    map_cache_s: float = Field(1, ge=0)
    history_window_h: int = Field(24, gt=0)
    readings_retention_days: int = Field(30, gt=0)
    push_max_attempts: int = Field(5, gt=0)

    def timers(self) -> Timers:
        return Timers(
            ghost=timedelta(seconds=self.ghost_s),
            debounce=timedelta(seconds=self.debounce_s),
            offline=timedelta(seconds=self.offline_s),
            human_fresh=timedelta(seconds=self.human_fresh_s),
            request_timeout=timedelta(seconds=self.request_timeout_s),
            host_end=timedelta(seconds=self.host_end_s),
            host_leave_cancel=timedelta(seconds=self.host_leave_cancel_s),
            match_timeout=timedelta(seconds=self.match_timeout_s),
            blink=timedelta(seconds=self.blink_s),
            session_max=timedelta(seconds=self.session_max_s),
            confirm_grace=timedelta(seconds=self.confirm_grace_s),
            sim_slot=timedelta(seconds=self.sim_slot_s),
            max_hosts_per_search=self.max_hosts_per_search,
            max_requests_per_hour=self.max_requests_per_hour,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # values come from the environment
