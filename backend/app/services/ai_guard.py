"""NFR-3 at the service boundary: any AI exception becomes the deterministic fallback.

Adapters own their timeouts; this guard makes sure a bug or an unexpected exception in any
adapter still never blocks a flow.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence

from app.domain.topic_rules import (
    ICEBREAKER_MAX,
    icebreaker_fallback,
    keyword_overlap,
    normalize_fallback,
)
from app.domain.types import Topic
from app.services.ports import HostTopic, TopicAI

log = logging.getLogger("ghostseats.ai")


class GuardedAI:
    def __init__(self, inner: TopicAI) -> None:
        self._inner = inner

    def normalize_topic(self, text: str) -> Topic:
        try:
            return self._inner.normalize_topic(text)
        except Exception as exc:
            log.warning("normalize_topic fell back: %s", type(exc).__name__)
            return normalize_fallback(text)

    def rank_hosts(self, seeker: Topic, hosts: Sequence[HostTopic]) -> dict[str, int]:
        try:
            scores = self._inner.rank_hosts(seeker, hosts)
            return {h.id: max(0, min(100, int(scores.get(h.id, 0)))) for h in hosts}
        except Exception as exc:
            log.warning("rank_hosts fell back: %s", type(exc).__name__)
            return {h.id: keyword_overlap(seeker.keywords, h.topic.keywords) for h in hosts}

    def icebreaker(self, a: Topic, b: Topic) -> str:
        try:
            text = self._inner.icebreaker(a, b).strip()
            if 0 < len(text) <= ICEBREAKER_MAX:
                return text
            log.warning("icebreaker out of bounds (%d chars); using fallback", len(text))
        except Exception as exc:
            log.warning("icebreaker fell back: %s", type(exc).__name__)
        return icebreaker_fallback(a, b)
