"""Serial bridge: the demo table's Arduino (IR sensor) → POST /api/readings (D39, HW-7..10).

    pip install -r bridge/requirements.txt
    GHOSTSEATS_URL=https://<host> NODE_KEY=<key> python bridge/arduino_bridge.py

The sketch (firmware/HACKATHON) prints "occupied: true|false ..." about 20 times a second and
drives its own LEDs. The bridge posts on every change and at least every HEARTBEAT_S, so the
backend never marks the seat offline while the sensor is connected.

One IR sensor cannot tell a person from a bag, so human_present mirrors object_present (Q14).
"""

from __future__ import annotations

import glob
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Any

import httpx

HEARTBEAT_S = 2.0  # HW-8: one reading every 2 s
REQUEST_TIMEOUT_S = 1.5
RETRY_S = 1.0
_LINE_RE = re.compile(r"\boccupied:\s*(true|false)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Config:
    readings_url: str
    node_key: str
    node_id: str
    seat_id: str
    serial_port: str | None


def load_config(env: dict[str, str]) -> Config:
    node_key = env.get("NODE_KEY", "")
    if not node_key:
        raise SystemExit("NODE_KEY must be set (the backend's NODE_KEY, never committed)")
    base = env.get("GHOSTSEATS_URL", "http://localhost:8000").rstrip("/")
    return Config(
        readings_url=f"{base}/api/readings",
        node_key=node_key,
        node_id=env.get("NODE_ID", "table-1"),
        seat_id=env.get("SEAT_ID", "t1-s1"),
        serial_port=env.get("SERIAL_PORT") or None,
    )


def parse_line(line: str) -> bool | None:
    """True/False from a sketch line, None for anything else (boot noise, partial lines)."""
    match = _LINE_RE.search(line)
    return None if match is None else match.group(1).lower() == "true"


def should_send(state: bool, last_state: bool | None, last_sent: float, now: float) -> bool:
    return state != last_state or now - last_sent >= HEARTBEAT_S


def payload(config: Config, occupied: bool) -> dict[str, Any]:
    return {
        "node_id": config.node_id,
        "readings": [
            {"seat_id": config.seat_id, "object_present": occupied, "human_present": occupied}
        ],
    }


def send(client: httpx.Client, config: Config, occupied: bool) -> None:
    try:
        response = client.post(
            config.readings_url,
            json=payload(config, occupied),
            headers={"X-Node-Key": config.node_key},
            timeout=REQUEST_TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        log(f"post failed: {type(exc).__name__}")  # HW-10: on failure, send nothing
        return
    if response.status_code == 200:
        led = response.json().get("leds", {}).get(config.seat_id)
        log(f"occupied={occupied} -> LED {led}")
    else:
        log(f"HTTP {response.status_code}")


def find_serial_port() -> str:
    ports = sorted(glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/ttyACM*"))
    if not ports:
        raise RuntimeError("no Arduino found (set SERIAL_PORT)")
    return ports[0]


def log(message: str) -> None:
    print(f"{time.strftime('%H:%M:%S')} {message}", flush=True)


def run(config: Config) -> None:
    import serial  # pyserial; imported here so the pure parts load without it

    last_state: bool | None = None
    last_sent = 0.0
    with httpx.Client() as client:
        while True:
            try:
                port = config.serial_port or find_serial_port()
                with serial.Serial(port, 115200, timeout=0.2) as device:
                    log(f"listening on {port}")
                    device.reset_input_buffer()
                    while True:
                        if device.in_waiting > 200:  # fell behind: skip to fresh lines
                            device.reset_input_buffer()
                        state = parse_line(device.readline().decode("utf-8", errors="replace"))
                        now = time.monotonic()
                        if state is not None and should_send(state, last_state, last_sent, now):
                            send(client, config, state)
                            last_state, last_sent = state, now
            except (serial.SerialException, RuntimeError) as exc:
                log(f"serial: {exc}; retrying in {RETRY_S:.0f} s")
                time.sleep(RETRY_S)


def main() -> int:
    config = load_config(dict(os.environ))
    log(f"{config.node_id}/{config.seat_id} -> {config.readings_url}")
    try:
        run(config)
    except KeyboardInterrupt:
        log("stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
