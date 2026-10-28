"""Write the compose demo's secrets to an env file on first start (D60).

python -m scripts.demo_env /state/demo.env

Generates SECRET_KEY, NODE_KEY and a VAPID pair, so the demo needs no setup and no secret is
ever committed. A file that already exists is left as it is, so sessions and push
subscriptions survive restarts. A key already set in the environment is used instead of a new
one (the e2e run passes NODE_KEY this way, so its test can post readings).
"""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path

from scripts.vapid_keys import generate as vapid_pair

KEYS = ("SECRET_KEY", "NODE_KEY", "VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY", "VAPID_SUBJECT")


def demo_values(env: dict[str, str]) -> dict[str, str]:
    public, private = vapid_pair()
    generated = {
        "SECRET_KEY": secrets.token_urlsafe(48),
        "NODE_KEY": secrets.token_urlsafe(24),
        "VAPID_PUBLIC_KEY": public,
        "VAPID_PRIVATE_KEY": private,
        "VAPID_SUBJECT": "mailto:demo@example.invalid",
    }
    return {key: env.get(key) or generated[key] for key in KEYS}


def write_once(path: Path, env: dict[str, str]) -> bool:
    """Creates the file with mode 600. Returns False when it already existed."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        for key, value in demo_values(env).items():
            f.write(f"{key}={value}\n")
    return True


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: python -m scripts.demo_env <path>", file=sys.stderr)
        return 2
    path = Path(argv[0])
    created = write_once(path, dict(os.environ))
    print(f"{'wrote' if created else 'kept'} {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
