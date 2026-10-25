"""Live check of Muse Spark with the key in .env (D38): one call per function, with latency.

uv run python -m scripts.muse_check

Calls MuseAI directly, without the fallback guard, so a failure shows its real cause. Exits 1 if
any call fails or takes longer than AI_TIMEOUT_S, which in the app would mean the fallback
answers instead.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.adapters.ai_muse import MuseAI, MuseError
from app.config import get_settings
from app.domain.types import Topic


@dataclass(frozen=True)
class _Host:
    id: str
    topic: Topic
    about_me: str | None


def _timed[T](name: str, call: Callable[[], T], budget_s: float) -> T | None:
    started = time.monotonic()
    try:
        result = call()
    except MuseError as exc:
        print(f"FAIL {name}: {exc}")
        return None
    elapsed = time.monotonic() - started
    verdict = "ok  " if elapsed <= budget_s else "SLOW"
    print(f"{verdict} {name} ({elapsed:.2f} s): {result}")
    return result if elapsed <= budget_s else None


def main() -> int:
    settings = get_settings()
    if settings.muse_api_key is None:
        print("MUSE_API_KEY is not set in .env", file=sys.stderr)
        return 2
    ai = MuseAI(
        settings.muse_api_key.get_secret_value(),
        settings.muse_base_url,
        settings.muse_model,
        settings.ai_timeout_s,
    )
    budget = settings.ai_timeout_s
    print(f"{settings.muse_model} at {settings.muse_base_url}, budget {budget:.1f} s per call")

    seeker = _timed("normalize_topic", lambda: ai.normalize_topic("orgo 1 exam prep"), budget)
    other = _timed("normalize_topic", lambda: ai.normalize_topic("314 trees hw"), budget)
    if seeker is None or other is None:
        return 1
    hosts = [
        _Host("host-a", seeker, "Working through SN2 vs SN1 problems"),
        _Host("host-b", other, None),
    ]
    ranked = _timed("rank_hosts", lambda: ai.rank_hosts(seeker, hosts), budget)
    icebreaker = _timed("icebreaker", lambda: ai.icebreaker(seeker, seeker), budget)
    return 0 if ranked is not None and icebreaker is not None else 1


if __name__ == "__main__":
    sys.exit(main())
