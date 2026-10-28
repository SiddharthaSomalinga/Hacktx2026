"""The operational scripts' pure parts: VAPID keys, demo env, QR sheet, fake-node payload,
seeding, cards."""

from __future__ import annotations

import base64
import re
import stat
from pathlib import Path

import pytest
from py_vapid import Vapid  # the class pywebpush signs with

from scripts import card_images
from scripts.demo_env import KEYS, write_once
from scripts.fake_node import STATES, FakeNode
from scripts.seat_qr import seat_url, sheet
from scripts.seed_history import sensed
from scripts.vapid_keys import generate
from tests.conftest import make_settings


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def test_vapid_keys_are_usable_by_pywebpush() -> None:
    public, private = generate()
    assert len(_unb64(public)) == 65 and _unb64(public)[0] == 4  # uncompressed P-256 point
    assert len(_unb64(private)) == 32
    loaded = Vapid.from_string(private_key=private)  # what pywebpush does with the env value
    headers = loaded.sign({"sub": "mailto:team@example.com", "aud": "https://push.example.com"})
    assert headers["Authorization"].startswith("vapid ")


def test_qr_sheet_escapes_and_links_each_seat() -> None:
    page = sheet("https://gs.example.com/", [("t1-s1", "PCL <Library>", "Table 01", 1)])
    assert seat_url("https://gs.example.com/", "t1-s1") == "https://gs.example.com/seat/t1-s1"
    assert "https://gs.example.com/seat/t1-s1" in page and "<svg" in page
    assert "PCL &lt;Library&gt;" in page


def test_fake_node_payload_matches_the_readings_contract() -> None:
    node = FakeNode("http://x", "table-1", ["t1-s1", "t1-s2"], "k")
    node.sensed["t1-s2"] = STATES["b"]
    assert node.payload() == {
        "node_id": "table-1",
        "readings": [
            {"seat_id": "t1-s1", "object_present": False, "human_present": False},
            {"seat_id": "t1-s2", "object_present": True, "human_present": False},
        ],
    }


def test_seeded_history_follows_busyness() -> None:
    quiet = sum(sensed(f"s{i}", 1, 10) == (False, False) for i in range(500))
    busy = sum(sensed(f"s{i}", 1, 90) == (False, False) for i in range(500))
    assert quiet > busy


def test_card_images_cover_every_card_key_and_reject_non_png() -> None:
    """Every key a match can point at has a scene, and a WebP answer is refused, not saved."""
    assert set(card_images.card_keys()) <= set(card_images.SCENES)
    assert "generic" in card_images.card_keys()
    png = card_images.PNG + b"rest"
    ok = {"data": [{"b64_json": base64.b64encode(png).decode()}]}
    assert card_images.parse_png(ok) == png
    webp = {"data": [{"b64_json": base64.b64encode(b"RIFF....WEBP").decode()}]}
    with pytest.raises(ValueError):
        card_images.parse_png(webp)


def test_demo_env_is_written_once_private_and_shell_safe(tmp_path: Path) -> None:
    path = tmp_path / "demo.env"
    assert write_once(path, {"NODE_KEY": "e2e-node-key-0123456789"})
    first = path.read_text()
    values = dict(line.split("=", 1) for line in first.splitlines())
    assert tuple(values) == KEYS and values["NODE_KEY"] == "e2e-node-key-0123456789"
    assert all(re.fullmatch(r"[A-Za-z0-9_@.:-]+", v) for v in values.values())  # sourced by sh
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    make_settings(**{k.lower(): v for k, v in values.items()})  # the app accepts every value
    assert not write_once(path, {})
    assert path.read_text() == first  # a restart keeps sessions and subscriptions valid
