"""Bridge between the physical Arduino USB serial output and Ghost Seats backend API."""

from __future__ import annotations

import glob
import sys
import time
import httpx
import serial

DEFAULT_URL = "http://localhost:8000/api/readings"
NODE_KEY = "ghost-seats-demo-node-key-16-chars"
NODE_ID = "table-1"
SEAT_ID = "t1-s1"


def find_serial_port() -> str:
    ports = glob.glob("/dev/cu.usbmodem*") + glob.glob("/dev/tty.usbmodem*")
    if not ports:
        raise RuntimeError("No Arduino USB serial device found in /dev/cu.usbmodem*")
    return ports[0]


def send_reading(client: httpx.Client, is_occupied: bool) -> None:
    payload = {
        "node_id": NODE_ID,
        "readings": [
            {
                "seat_id": SEAT_ID,
                "object_present": is_occupied,
                "human_present": is_occupied,
            }
        ],
    }
    headers = {
        "Content-Type": "application/json",
        "X-Node-Key": NODE_KEY,
    }
    try:
        r = client.post(DEFAULT_URL, json=payload, headers=headers, timeout=1.5)
        if r.status_code == 200:
            print(f"[BRIDGE -> API] State={is_occupied} -> LED: {r.json().get('leds', {}).get(SEAT_ID)}")
        else:
            print(f"[BRIDGE -> API ERROR] HTTP {r.status_code}: {r.text}")
    except Exception as exc:
        print(f"[BRIDGE -> API ERROR] {exc}")


def run_bridge() -> None:
    port = find_serial_port()
    print(f"[BRIDGE] Opening Arduino connection on {port} at 115200 baud...")
    client = httpx.Client()

    last_state = None
    last_send_time = 0.0

    while True:
        try:
            with serial.Serial(port, 115200, timeout=0.2) as ser:
                print("[BRIDGE] Connected! Listening for IR sensor changes...")
                time.sleep(1.0)
                ser.reset_input_buffer()

                while True:
                    # If buffer accumulated old readings, jump to the freshest reading
                    if ser.in_waiting > 200:
                        ser.reset_input_buffer()

                    raw = ser.readline().decode("utf-8", errors="replace").strip()
                    if not raw:
                        continue

                    is_occupied = None
                    lowered = raw.lower()
                    if "occupied: true" in lowered or "occupied (a1 green on" in lowered:
                        is_occupied = True
                    elif "occupied: false" in lowered or "not occupied" in lowered:
                        is_occupied = False

                    if is_occupied is not None:
                        now = time.time()
                        # Send immediately when state flips, or send heartbeat every 1s
                        if is_occupied != last_state or (now - last_send_time >= 1.0):
                            last_state = is_occupied
                            last_send_time = now
                            send_reading(client, is_occupied)

        except serial.SerialException as exc:
            print(f"[BRIDGE] Serial error: {exc}. Retrying in 1s...")
            time.sleep(1.0)
        except Exception as exc:
            print(f"[BRIDGE] Unexpected error: {exc}. Retrying in 1s...")
            time.sleep(1.0)


def main() -> int:
    try:
        run_bridge()
    except KeyboardInterrupt:
        print("\n[BRIDGE] Stopped by user.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
