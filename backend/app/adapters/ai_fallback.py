"""FallbackAI: the deterministic TopicAI used when Muse is absent, slow or wrong (D7, NFR-3)."""

from __future__ import annotations

from collections.abc import Sequence

from app.domain.topic_rules import icebreaker_fallback, keyword_overlap, normalize_fallback
from app.domain.types import Topic
from app.services.ports import HostTopic


class FallbackAI:
    def normalize_topic(self, text: str) -> Topic:
        return normalize_fallback(text)

    def rank_hosts(self, seeker: Topic, hosts: Sequence[HostTopic]) -> dict[str, int]:
        return {h.id: keyword_overlap(seeker.keywords, h.topic.keywords) for h in hosts}

    def icebreaker(self, a: Topic, b: Topic) -> str:
        return icebreaker_fallback(a, b)
