"""Topic normalization with the `topic_cache` in front of the AI (FR-18, REQUIREMENTS §9)."""

from __future__ import annotations

from app.domain.topic_rules import cache_key
from app.domain.types import Topic
from app.services.context import Context


class TopicsService:
    def __init__(self, ctx: Context) -> None:
        self._ctx = ctx

    def normalize(self, raw: str) -> Topic:
        key = cache_key(raw)
        with self._ctx.repo.read() as tx:
            cached = tx.cached_topic(key)
        if cached is not None:
            return cached
        topic = self._ctx.ai.normalize_topic(raw)  # outside any transaction (≤ AI_TIMEOUT_S)
        with self._ctx.repo.tx() as tx:
            tx.cache_topic(key, topic)
        return topic
