"""The live stream's vocabulary (D61): which topics a change touches, and event versions."""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from app.domain.types import LiveTopic, UserChange

_ALL = frozenset(LiveTopic)

# The client refetches exactly these queries. `me` carries the host status and the search and
# match ids; `inbox` the host's pending requests; `search` and `match` their own views.
TOPICS: Mapping[UserChange, frozenset[LiveTopic]] = {
    UserChange.SESSION: frozenset({LiveTopic.ME, LiveTopic.INBOX}),
    UserChange.SEARCH: frozenset({LiveTopic.ME, LiveTopic.SEARCH}),
    UserChange.REQUEST: frozenset({LiveTopic.SEARCH, LiveTopic.INBOX}),
    UserChange.MATCH: frozenset({LiveTopic.ME, LiveTopic.MATCH, LiveTopic.SEARCH}),
    UserChange.SEAT: frozenset({LiveTopic.ME, LiveTopic.MATCH}),
    UserChange.TIME: frozenset({LiveTopic.ME, LiveTopic.MATCH}),
    UserChange.BLOCK: _ALL,
}

_NONE = "-"
_HEX = frozenset("0123456789abcdef")


def topics_for(changes: Iterable[UserChange]) -> frozenset[LiveTopic]:
    out: frozenset[LiveTopic] = frozenset()
    for change in changes:
        out |= TOPICS[change]
    return out


def version_of(etag: str) -> str:
    """A snapshot's version is its ETag without the quotes."""
    return etag.strip('"')


def format_version(buildings: str | None, building: str | None) -> str:
    """An event id: both snapshot versions, so one Last-Event-ID covers both."""
    return f"{buildings or _NONE}.{building or _NONE}"


def parse_version(raw: str | None) -> tuple[str | None, str | None]:
    """The versions a reconnecting client already has. Anything malformed means none."""
    if raw is None:
        return None, None
    parts = raw.split(".")
    if len(parts) != 2:
        return None, None
    a, b = (_part(p) for p in parts)
    return a, b


def _part(text: str) -> str | None:
    if text == _NONE or not text or len(text) > 64 or not set(text) <= _HEX:
        return None
    return text
