"""Live hints shared by both repositories (D61): what a transaction recorded, and the wire format.

A transaction's writers record raw facts here: which seats changed and how, which users and
host sessions were written. At commit the repository resolves them into hints (a seat's
building, the hosts at its table, the people whose alternative seat is on its floor) and
sends them. Payloads are short text, one per hint:

    m:<building id>
    u:<user id>:<change>,<change>,...
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.types import SeatChange, UserChange
from app.services.ports import Hint, MapHint, UserHint

CHANNEL = "synapse_live"

_RANK = {SeatChange.NONE: 0, SeatChange.PRESENCE: 1, SeatChange.PUBLIC: 2}


@dataclass
class PendingHints:
    seats: dict[str, SeatChange] = field(default_factory=dict)
    users: dict[str, set[UserChange]] = field(default_factory=dict)
    host_sessions: dict[str, set[UserChange]] = field(default_factory=dict)

    def seat(self, seat_id: str, change: SeatChange) -> None:
        if _RANK[change] > _RANK[self.seats.get(seat_id, SeatChange.NONE)]:
            self.seats[seat_id] = change

    def user(self, user_id: str, change: UserChange) -> None:
        self.users.setdefault(user_id, set()).add(change)

    def host(self, session_id: str, change: UserChange) -> None:
        """A user known only by their host session; resolved to the user at commit."""
        self.host_sessions.setdefault(session_id, set()).add(change)

    def __bool__(self) -> bool:
        return bool(self.seats or self.users or self.host_sessions)


def encode(hint: MapHint | UserHint) -> str:
    if isinstance(hint, MapHint):
        return f"m:{hint.building_id}"
    return f"u:{hint.user_id}:{','.join(sorted(hint.changes))}"


def decode(payload: str) -> Hint | None:
    """None for anything this version doesn't understand, including the feed's own probes."""
    kind, _, rest = payload.partition(":")
    if kind == "m" and rest:
        return MapHint(rest)
    if kind == "u":
        user_id, _, changes = rest.rpartition(":")
        try:
            parsed = frozenset(UserChange(c) for c in changes.split(","))
        except ValueError:
            return None
        return UserHint(user_id, parsed) if user_id else None
    return None


def merge(hints: list[MapHint | UserHint]) -> list[MapHint | UserHint]:
    """One hint per building and one per user, in a stable order."""
    buildings = sorted({h.building_id for h in hints if isinstance(h, MapHint)})
    users: dict[str, set[UserChange]] = {}
    for h in hints:
        if isinstance(h, UserHint):
            users.setdefault(h.user_id, set()).update(h.changes)
    return [MapHint(b) for b in buildings] + [
        UserHint(u, frozenset(c)) for u, c in sorted(users.items())
    ]
