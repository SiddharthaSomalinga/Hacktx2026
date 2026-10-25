"""Printable QR sheet: one code per real seat, opening <origin>/seat/<seat_id> (FR-21).

uv run python -m scripts.seat_qr --origin https://ghostseats.example.com
→ out/seat-qr.html (print it, cut, stick one code on each seat)
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from urllib.parse import urlparse

import psycopg
import segno

from app.config import get_settings


def seat_url(origin: str, seat_id: str) -> str:
    return f"{origin.rstrip('/')}/seat/{seat_id}"


def sheet(origin: str, seats: list[tuple[str, str, str, int]]) -> str:
    cards = []
    for seat_id, building, table, position in seats:
        url = seat_url(origin, seat_id)
        svg = segno.make(url, error="m").svg_inline(scale=5, dark="#000", light="#fff")
        caption = (
            f"<b>{html.escape(building)}</b><br>{html.escape(table)} · seat {position}"
            f"<br><small>{html.escape(url)}</small>"
        )
        cards.append(f"<figure>{svg}<figcaption>{caption}</figcaption></figure>")
    return f"""<!doctype html><meta charset="utf-8"><title>Seat QR codes</title>
<style>body{{font-family:system-ui,sans-serif;display:grid;grid-template-columns:repeat(3,1fr);gap:24px;padding:24px}}
figure{{margin:0;text-align:center;border:1px dashed #999;padding:12px;break-inside:avoid}}
small{{word-break:break-all;color:#555}}</style>
{"".join(cards)}"""


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--origin", required=True, help="public https origin the phones open")
    parser.add_argument("--out", type=Path, default=Path("out/seat-qr.html"))
    args = parser.parse_args(argv)
    parsed = urlparse(args.origin)
    if parsed.scheme not in ("https", "http") or not parsed.netloc:
        print("--origin must be a full URL like https://example.com", file=sys.stderr)
        return 2
    with psycopg.connect(get_settings().database_url) as conn:
        seats = conn.execute(
            b"""SELECT s.id, b.name, t.label, s.position FROM seats s
                JOIN tables t ON t.id = s.table_id JOIN buildings b ON b.id = t.building_id
                WHERE NOT s.is_simulated ORDER BY b.name, t.label, s.position"""
        ).fetchall()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(sheet(args.origin, seats), encoding="utf-8")
    print(f"wrote {len(seats)} codes to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
