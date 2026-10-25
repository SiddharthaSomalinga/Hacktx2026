"""Drives the API like the real system: a node posting every 2 s and several logged-in phones."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import NODE_KEY
from tests.fakes import FakeClock
from tests.world import NODE, REAL_SEATS

BAG = (True, False)
PERSON = (True, True)
EMPTY = (False, False)


class Node:
    """The physical table: holds what each seat senses and posts it like the bridge."""

    def __init__(self, app: FastAPI, clock: FakeClock) -> None:
        self.http = TestClient(app)
        self.clock = clock
        self.state: dict[str, tuple[bool, bool]] = dict.fromkeys(REAL_SEATS, EMPTY)
        self.leds: dict[str, str] = {}
        self.online = True

    def set(self, seat: str, sensed: tuple[bool, bool]) -> None:
        self.state[seat] = sensed

    def post(self) -> dict[str, str]:
        readings = [
            {"seat_id": s, "object_present": o, "human_present": h}
            for s, (o, h) in self.state.items()
        ]
        r = self.http.post(
            "/api/readings",
            json={"node_id": NODE, "readings": readings},
            headers={"X-Node-Key": NODE_KEY},
        )
        assert r.status_code == 200, r.text
        self.leds = r.json()["leds"]
        return self.leds

    def run(
        self, seconds: float, every: float = 2.0, on_tick: Callable[[], None] | None = None
    ) -> None:
        """Let `seconds` pass, posting every `every` seconds while online."""
        elapsed = 0.0
        while elapsed < seconds:
            step = min(every, seconds - elapsed)
            self.clock.advance(step)
            elapsed += step
            if self.online:
                self.post()
            if on_tick:
                on_tick()


class Phone:
    """One user's browser: its own cookie jar."""

    def __init__(self, app: FastAPI, user_id: str | None = None) -> None:
        self.http = TestClient(app)
        if user_id is not None:
            r = self.http.post("/api/login", json={"user_id": user_id})
            assert r.status_code == 200, r.text

    def get(self, path: str, **kw: Any) -> Any:
        return self.http.get(path, **kw)

    def post(self, path: str, json: Any = None) -> Any:
        return self.http.post(path, json=json)

    def ok(self, method: str, path: str, json: Any = None) -> Any:
        r = self.http.request(method, path, json=json)
        assert r.status_code == 200, f"{method} {path} → {r.status_code} {r.text}"
        return r.json()

    def error(self, method: str, path: str, json: Any = None) -> tuple[int, str]:
        r = self.http.request(method, path, json=json)
        assert r.status_code >= 400, f"expected an error, got {r.status_code} {r.text}"
        return r.status_code, r.json()["error"]
