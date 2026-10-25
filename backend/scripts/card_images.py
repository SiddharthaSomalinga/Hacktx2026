"""Generate the match card images with Muse Image (REQUIREMENTS §9, D52).

uv run python -m scripts.card_images [--out out/cards]

One picture per subject in the catalog plus `generic`, named by `card_key_for` so they match
`card_url` (`/cards/<key>.png`). No people and no text: the client overlays names and the
icebreaker. Writes `<key>.png` and `cards.json` (model, prompt, sha256) for provenance. A person
reviews every image before it is copied into the frontend's public/cards/.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.config import get_settings
from app.domain.catalog import DEPARTMENT_SUBJECT
from app.domain.topic_rules import card_key_for

MODEL = "muse-image-1.0"
PNG = b"\x89PNG\r\n\x1a\n"

STYLE = (
    "Fine-line architectural illustration, top-down drafting style, warm off-white paper "
    "background, thin charcoal ink lines with one burnt-orange accent, calm and minimal, "
    "lots of empty space. Absolutely no people, no faces, no hands, no text, no letters, "
    "no numbers, no logos."
)

SCENES: dict[str, str] = {
    "biology": "a leaf, a cell diagram and a microscope on a library study table",
    "chemistry": "glass flasks, a benzene ring model and a notebook on a library study table",
    "computer-science": "a laptop, a tree diagram drawn as nodes and a coffee cup on a study table",
    "economics": "supply and demand curves sketched on paper beside a calculator on a study table",
    "mathematics": "a compass, a protractor and geometric figures on a library study table",
    "physics": "a pendulum, a magnet and wave diagrams on a library study table",
    "psychology": "a brain model, sticky notes and an open journal on a library study table",
    "statistics": "a bell curve, dice and a scatter of points on paper on a study table",
    "generic": "a long library study table with open books, pencils and empty chairs",
}


def card_keys() -> list[str]:
    """Every key `card_key_for` can return, so no match ever points at a missing image."""
    return sorted({card_key_for(s) for s in DEPARTMENT_SUBJECT.values()} | {"generic"})


def request_body(key: str) -> dict[str, object]:
    return {
        "model": MODEL,
        "prompt": f"{SCENES[key]}. {STYLE}",
        "n": 1,
        "size": "1536x1024",
        "output_format": "png",
        "response_format": "b64_json",
    }


def parse_png(payload: dict[str, object]) -> bytes:
    """The single image in a generations response, checked to really be a PNG."""
    data = payload.get("data")
    if not isinstance(data, list) or len(data) != 1 or not isinstance(data[0], dict):
        raise ValueError("expected exactly one image")
    raw = base64.b64decode(str(data[0].get("b64_json", "")), validate=True)
    if not raw.startswith(PNG):
        raise ValueError("the image is not a PNG")
    return raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("out/cards"))
    args = parser.parse_args()
    settings = get_settings()
    if settings.muse_api_key is None:
        print("MUSE_API_KEY is not set", file=sys.stderr)
        return 1
    missing = set(card_keys()) - set(SCENES)
    if missing:
        print(f"no scene for: {', '.join(sorted(missing))}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    provenance: dict[str, object] = {"model": MODEL, "style": STYLE, "cards": {}}
    headers = {"Authorization": f"Bearer {settings.muse_api_key.get_secret_value()}"}
    url = settings.muse_base_url.rstrip("/") + "/images/generations"
    with httpx.Client(timeout=180, headers=headers) as client:
        for key in card_keys():
            body = request_body(key)
            response = client.post(url, json=body)
            if response.status_code != 200:
                print(f"FAIL {key}: HTTP {response.status_code}", file=sys.stderr)
                return 1
            png = parse_png(response.json())
            (args.out / f"{key}.png").write_bytes(png)
            cards = provenance["cards"]
            assert isinstance(cards, dict)
            cards[key] = {
                "prompt": body["prompt"],
                "sha256": hashlib.sha256(png).hexdigest(),
                "generated": datetime.now(UTC).isoformat(timespec="seconds"),
            }
            print(f"ok   {key} ({len(png) // 1024} KiB)")
    (args.out / "cards.json").write_text(json.dumps(provenance, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
