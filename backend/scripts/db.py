"""Apply SQL files and Timescale policies to DATABASE_URL (no psql needed).

python -m scripts.db apply sql/schema.sql
python -m scripts.db policies
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg


def _url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        from app.config import get_settings

        url = get_settings().database_url
    return url


def apply(path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    with psycopg.connect(_url(), autocommit=True) as conn:
        conn.execute(sql.encode())  # bytes: run as a multi-statement script
    print(f"applied {path}")


def policies() -> None:
    from app.adapters.history_sql import policy_statements
    from app.config import get_settings

    settings = get_settings()
    with psycopg.connect(_url(), autocommit=True) as conn:
        for statement in policy_statements(settings.readings_retention_days, settings.offline_s):
            conn.execute(statement.encode())
    print("policies applied")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("apply").add_argument("path", type=Path)
    sub.add_parser("policies")
    args = parser.parse_args(argv)
    if args.cmd == "apply":
        apply(args.path)
    else:
        policies()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
