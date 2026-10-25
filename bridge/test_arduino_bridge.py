"""The bridge's parsing, send decision, config and payload (D39); no Arduino needed.

cd bridge && ../backend/.venv/bin/python -m pytest -q
"""

from __future__ import annotations

import httpx
import pytest
from arduino_bridge import HEARTBEAT_S, load_config, parse_line, payload, send, should_send

SKETCH_TRUE = "occupied: true  -> OCCUPIED (A1 Green ON, A2 Blue OFF)"
SKETCH_FALSE = "occupied: false -> NOT OCCUPIED (A1 Green OFF, A2 Blue ON)"


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        (SKETCH_TRUE, True),
        (SKETCH_FALSE, False),
        ("OCCUPIED: TRUE\r\n", True),
        ("ccupied: false -> NOT OC", None),  # a line cut off mid-word at connect time
        ("", None),
        ("\x00\xff garbage", None),
    ],
)
def test_parse_line(line: str, expected: bool | None) -> None:
    assert parse_line(line) is expected


def test_sends_on_change_and_on_heartbeat_only() -> None:
    assert should_send(True, None, 0.0, 0.0)  # first reading
    assert should_send(False, True, 10.0, 10.1)  # change
    assert not should_send(True, True, 10.0, 10.0 + HEARTBEAT_S - 0.01)
    assert should_send(True, True, 10.0, 10.0 + HEARTBEAT_S)


def test_config_requires_a_key_and_builds_the_url() -> None:
    with pytest.raises(SystemExit):
        load_config({})
    config = load_config({"NODE_KEY": "k" * 16, "GHOSTSEATS_URL": "https://gs.example/"})
    assert config.readings_url == "https://gs.example/api/readings"
    assert (config.node_id, config.seat_id, config.serial_port) == ("table-1", "t1-s1", None)


def test_payload_matches_the_readings_contract() -> None:
    config = load_config({"NODE_KEY": "k" * 16})
    assert payload(config, True) == {
        "node_id": "table-1",
        "readings": [{"seat_id": "t1-s1", "object_present": True, "human_present": True}],
    }


def test_send_survives_a_dead_backend(capsys: pytest.CaptureFixture[str]) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with httpx.Client(transport=httpx.MockTransport(refuse)) as client:
        send(client, load_config({"NODE_KEY": "k" * 16}), True)
    assert "post failed: ConnectError" in capsys.readouterr().out
