"""Interactive stand-in for the Pi bridge: posts the same payload every 2 s (HW-3, HW-8).

    uv run python -m scripts.fake_node --seats t1-s1,t1-s2
    > 1 p      seat 1 has a person (object + human)
    > 2 b      seat 2 has only a bag (object, no human)
    > 1 e      seat 1 is empty
    > q        quit

Prints the LED colors the backend returns whenever they change.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading

import httpx

STATES = {"p": (True, True), "b": (True, False), "e": (False, False), "h": (False, True)}


class FakeNode:
    def __init__(self, base_url: str, node_id: str, seats: list[str], key: str) -> None:
        self.url = base_url.rstrip("/") + "/api/readings"
        self.node_id = node_id
        self.seats = seats
        self.headers = {"X-Node-Key": key}
        self.sensed = dict.fromkeys(seats, STATES["e"])
        self.last_leds: dict[str, str] = {}
        self.lock = threading.Lock()

    def payload(self) -> dict[str, object]:
        with self.lock:
            return {
                "node_id": self.node_id,
                "readings": [
                    {"seat_id": s, "object_present": o, "human_present": h}
                    for s, (o, h) in self.sensed.items()
                ],
            }

    def post(self, client: httpx.Client) -> dict[str, str] | None:
        try:
            r = client.post(self.url, json=self.payload(), headers=self.headers, timeout=3)
        except httpx.HTTPError as exc:
            print(
                f"  backend unreachable ({type(exc).__name__}); the node would go local", flush=True
            )
            return None
        if r.status_code != 200:
            print(f"  {r.status_code} {r.text}", flush=True)
            return None
        leds: dict[str, str] = r.json()["leds"]
        return leds

    def loop(self, stop: threading.Event, every_s: float) -> None:
        with httpx.Client() as client:
            while not stop.is_set():
                leds = self.post(client)
                if leds is not None and leds != self.last_leds:
                    shown = "  ".join(f"{s}={c}" for s, c in sorted(leds.items()))
                    print(f"  LEDs: {shown}", flush=True)
                    self.last_leds = leds
                stop.wait(every_s)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--node-id", default="table-1")
    parser.add_argument("--seats", default="t1-s1,t1-s2", help="seat ids in node order")
    parser.add_argument("--every", type=float, default=2.0)
    args = parser.parse_args(argv)
    key = os.environ.get("NODE_KEY")
    if not key:
        print("NODE_KEY must be set (same value as the backend's)", file=sys.stderr)
        return 2
    node = FakeNode(args.base_url, args.node_id, args.seats.split(","), key)
    stop = threading.Event()
    thread = threading.Thread(target=node.loop, args=(stop, args.every), daemon=True)
    thread.start()
    print(__doc__.split("\n\n", 1)[1], flush=True)
    try:
        for line in sys.stdin:
            parts = line.split()
            if parts == ["q"]:
                break
            if len(parts) != 2 or parts[1] not in STATES or not parts[0].isdigit():
                print("  usage: <seat number> <p|b|e|h>, or q", flush=True)
                continue
            index = int(parts[0]) - 1
            if not 0 <= index < len(node.seats):
                print(f"  seat number must be 1..{len(node.seats)}", flush=True)
                continue
            with node.lock:
                node.sensed[node.seats[index]] = STATES[parts[1]]
    except KeyboardInterrupt:
        pass
    stop.set()
    thread.join(timeout=5)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
