"""The live stream (D61): one hub per process fans snapshots and per-user hints out to streams.

The hub watches a snapshot (the buildings list, or one building) while at least one stream
here needs it. It rebuilds each watched snapshot every LIVE_CHECK_S, which catches what time
alone changes (ghost timer, offline, simulation slots), and at once when a hint marks it
dirty. A rebuild whose ETag differs is offered to every watching stream. The work depends on
the number of watched snapshots, never on the number of phones.

Everything here is derived: snapshots are re-read from the database, hints only say when to
look, and a new stream is never served a snapshot older than MAP_CACHE_S (NFR-8).

Each stream holds one slot per snapshot and a set of pending topics, so a client that reads
slowly skips states instead of queueing them.
"""

from __future__ import annotations

import json
import logging
import math
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import anyio
import anyio.to_thread

from app.domain.live import format_version, parse_version, topics_for, version_of
from app.domain.types import LiveTopic
from app.services.context import Context
from app.services.errors import DomainError, not_found
from app.services.map import MapService
from app.services.ports import Hint, Lost, MapHint, Resync, Unavailable, UserHint
from app.services.views import Cached

log = logging.getLogger("ghostseats.live")

BUILDINGS = "*"  # the buildings list's key; every other key is a building id


@dataclass(frozen=True)
class LiveEvent:
    kind: str  # buildings | building | invalidate | ping
    data: str
    id: str


@dataclass(eq=False)
class _Snapshot:
    cached: Cached | None = None
    ok: bool = False  # the last rebuild succeeded
    dirty: bool = True
    built_at: float = -math.inf
    confirmed_at: float = -math.inf
    broadcast_at: float = -math.inf
    started: int = 0  # rebuilds started; a late, older one never replaces a newer one
    applied: int = 0
    watchers: set[Subscription] = field(default_factory=set)


class Subscription:
    """One open stream. Only the hub's event loop touches it."""

    def __init__(
        self,
        hub: LiveHub,
        user_id: str | None,
        building_id: str | None,
        have: tuple[str | None, str | None],
    ) -> None:
        self.user_id = user_id
        self.building_id = building_id
        self.keys = (BUILDINGS,) if building_id is None else (BUILDINGS, building_id)
        self._hub = hub
        self._sent: dict[str, str | None] = {BUILDINGS: have[0]}  # what the client holds
        if building_id is not None:
            self._sent[building_id] = have[1]
        self._slots: dict[str, Cached] = {}
        self._topics: set[LiveTopic] = set()
        self._wake = anyio.Event()

    def offer(self, key: str, cached: Cached) -> None:
        if version_of(cached.etag) == self._sent.get(key):
            self._slots.pop(key, None)  # the client already has exactly this
        else:
            self._slots[key] = cached
        self._wake.set()

    def invalidate(self, topics: frozenset[LiveTopic]) -> None:
        if self.user_id is not None:  # anonymous streams never get per-user events
            self._topics |= topics
            self._wake.set()

    def _id(self) -> str:
        building = self._sent.get(self.building_id) if self.building_id else None
        return format_version(self._sent[BUILDINGS], building)

    async def events(self) -> AsyncIterator[LiveEvent]:
        """Snapshots and invalidations as they come; a ping after LIVE_PING_S of quiet. The
        first round never waits, so a client that already has everything gets a ping."""
        first = True
        while True:
            if not first and not (self._slots or self._topics):
                with anyio.move_on_after(self._hub.ping_s):
                    await self._wake.wait()
            first = False
            self._wake = anyio.Event()  # offers from here on wake the next round
            sent = False
            for key in self.keys:
                cached = self._slots.pop(key, None)
                if cached is not None:
                    self._sent[key] = version_of(cached.etag)
                    kind = "buildings" if key == BUILDINGS else "building"
                    yield LiveEvent(kind, cached.content.decode(), self._id())
                    sent = True
            if self._topics:
                topics, self._topics = sorted(self._topics), set()
                yield LiveEvent("invalidate", json.dumps(topics), self._id())
                sent = True
            if not sent:
                yield LiveEvent("ping", json.dumps(self._hub.health(self)), self._id())


class LiveHub:
    def __init__(self, ctx: Context, map_service: MapService) -> None:
        self._ctx = ctx
        self._map = map_service
        self._snapshots: dict[str, _Snapshot] = {}
        self._by_user: dict[str, set[Subscription]] = {}
        self._dirty: anyio.Event | None = None  # created on the hub's own event loop
        self._limiter: anyio.CapacityLimiter | None = None
        self._running = False
        self._resynced = False
        self.hints_ok = False

    @property
    def ping_s(self) -> float:
        return self._ctx.live_ping_s

    @property
    def watched(self) -> int:
        return sum(1 for s in self._snapshots.values() if s.watchers)

    # --- lifecycle -----------------------------------------------------------

    async def run(self) -> None:
        """The hub's two loops, until cancelled. Run once per process, from the lifespan."""
        self._dirty = anyio.Event()
        # One rebuild at a time, on threads apart from the routes' pool of 40.
        self._limiter = anyio.CapacityLimiter(1)
        self._running = True
        try:
            async with anyio.create_task_group() as tg:
                tg.start_soon(self._consume_hints)
                tg.start_soon(self._check_loop)
        finally:
            self._running = False
            self.hints_ok = False

    async def _consume_hints(self) -> None:
        while True:
            try:
                async for hint in self._ctx.repo.hints():
                    self.on_hint(hint)
            except Exception:
                log.exception("live hint feed failed; restarting it")
                self.hints_ok = False
                await anyio.sleep(1)

    async def _check_loop(self) -> None:
        while True:
            assert self._dirty is not None
            with anyio.move_on_after(self._ctx.live_check_s):
                await self._dirty.wait()
            self._dirty = anyio.Event()
            await self.run_once()

    # --- hints ---------------------------------------------------------------

    def on_hint(self, hint: Hint) -> None:
        if isinstance(hint, MapHint):
            for key in (BUILDINGS, hint.building_id):
                if (snapshot := self._snapshots.get(key)) is not None:
                    snapshot.dirty = True
            self._wake_checks()
        elif isinstance(hint, UserHint):
            topics = topics_for(hint.changes)
            for sub in self._by_user.get(hint.user_id, ()):
                sub.invalidate(topics)
        elif isinstance(hint, Resync):
            # Hints may have been missed: re-read every snapshot, and after a reconnect tell
            # every logged-in stream to refetch everything.
            self.hints_ok = True
            for snapshot in self._snapshots.values():
                snapshot.dirty = True
            if self._resynced:
                everything = frozenset(LiveTopic)
                for subs in self._by_user.values():
                    for sub in subs:
                        sub.invalidate(everything)
            self._resynced = True
            self._wake_checks()
        elif isinstance(hint, Lost):
            self.hints_ok = False

    def _wake_checks(self) -> None:
        if self._dirty is not None:
            self._dirty.set()

    # --- snapshots -----------------------------------------------------------

    async def run_once(self) -> None:
        """One pass over the watched snapshots. A dirty one is rebuilt at once, unless it was
        broadcast less than LIVE_CHECK_S ago: under churn, the periodic pass sends it."""
        now = self._ctx.clock.monotonic()
        gap = self._ctx.live_check_s
        for key, snapshot in list(self._snapshots.items()):
            if not snapshot.watchers:
                continue
            periodic = now - snapshot.built_at >= gap
            if not (periodic or snapshot.dirty):
                continue
            if not periodic and now - snapshot.broadcast_at < gap:
                continue
            await self._refresh(key, snapshot, now)

    def _build(self, key: str) -> Cached:
        if key == BUILDINGS:
            return self._map.buildings(fresh=True)
        return self._map.building(key, fresh=True)

    async def _rebuild(self, key: str, snapshot: _Snapshot, now: float) -> None:
        """Rebuild and broadcast; errors propagate to the caller."""
        snapshot.dirty = False
        snapshot.built_at = now
        snapshot.started += 1
        seq = snapshot.started
        try:
            cached = await anyio.to_thread.run_sync(self._build, key, limiter=self._limiter)
        except BaseException:
            if seq > snapshot.applied:
                snapshot.ok = False
            raise
        if seq <= snapshot.applied:
            return
        snapshot.applied = seq
        snapshot.ok = True
        snapshot.confirmed_at = now
        if snapshot.cached is None or cached.etag != snapshot.cached.etag:
            snapshot.cached = cached
            if snapshot.watchers:  # a first build for a first stream doesn't use up the gap
                snapshot.broadcast_at = now
            for sub in snapshot.watchers:
                sub.offer(key, cached)

    async def _refresh(self, key: str, snapshot: _Snapshot, now: float) -> None:
        try:
            await self._rebuild(key, snapshot, now)
        except (Unavailable, DomainError) as exc:  # database down, or the building is gone
            log.warning("live snapshot %s not rebuilt: %s", key, type(exc).__name__)
        except Exception:
            log.exception("live snapshot %s failed", key)

    def health(self, sub: Subscription) -> dict[str, bool]:
        """What a ping vouches for: the stream's snapshots were rebuilt successfully, and
        hints are arriving (if not, the client polls its per-user state)."""
        db = all(self._snapshots[k].ok for k in sub.keys if k in self._snapshots)
        return {"db": db, "hints": self.hints_ok}

    # --- streams -------------------------------------------------------------

    async def subscribe(
        self, user_id: str | None, building_id: str | None, have: tuple[str | None, str | None]
    ) -> Subscription:
        """Raises before anything is streamed: 404 for an unknown building, 503 if the
        database is down, so the client gets the usual JSON error."""
        if not self._running:
            raise not_found("live_disabled", "The live stream is not running; poll instead")
        sub = Subscription(self, user_id, building_id, have)
        now = self._ctx.clock.monotonic()
        for key in sub.keys:
            snapshot = self._snapshots.setdefault(key, _Snapshot())
            stale = now - snapshot.confirmed_at > self._ctx.map_cache_s
            if snapshot.cached is None or not snapshot.ok or stale:
                try:
                    await self._rebuild(key, snapshot, now)
                except BaseException:
                    if not snapshot.watchers:
                        del self._snapshots[key]
                    self._drop(sub)
                    raise
            snapshot.watchers.add(sub)
            assert snapshot.cached is not None
            sub.offer(key, snapshot.cached)
        if user_id is not None:
            self._by_user.setdefault(user_id, set()).add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        self._drop(sub)

    def _drop(self, sub: Subscription) -> None:
        for key in sub.keys:
            snapshot = self._snapshots.get(key)
            if snapshot is not None:
                snapshot.watchers.discard(sub)
                if not snapshot.watchers:
                    del self._snapshots[key]
        if sub.user_id is not None and (subs := self._by_user.get(sub.user_id)):
            subs.discard(sub)
            if not subs:
                del self._by_user[sub.user_id]


class LiveService:
    def __init__(self, ctx: Context, hub: LiveHub) -> None:
        self._ctx = ctx
        self.hub = hub

    async def open(
        self, user_id: str | None, building_id: str | None, last_event_id: str | None
    ) -> Subscription:
        if not self._ctx.live_enabled:
            raise not_found("live_disabled", "The live stream is off; poll instead")
        return await self.hub.subscribe(user_id, building_id, parse_version(last_event_id))

    def close(self, sub: Subscription) -> None:
        self.hub.unsubscribe(sub)

    def retry_ms(self) -> int:
        """The reconnect delay a stream suggests, jittered so a restart doesn't bring every
        phone back in the same instant."""
        return round(self._ctx.live_retry_s * 1000 * random.uniform(0.5, 1.5))

    @property
    def stall_s(self) -> float:
        return self._ctx.live_stall_s
