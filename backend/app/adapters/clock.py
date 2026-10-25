"""The real clock. Domain code never calls this; services receive it as a port."""

from __future__ import annotations

import time
from datetime import UTC, datetime


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()
