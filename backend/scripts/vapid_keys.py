"""Generate a VAPID key pair for web push (FR-51). Paste the output into .env; never commit it.

uv run python -m scripts.vapid_keys
"""

from __future__ import annotations

import base64
import sys

from cryptography.hazmat.primitives import serialization
from py_vapid import Vapid01


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def generate() -> tuple[str, str]:
    """(public applicationServerKey, private key), both base64url as browsers and pywebpush
    expect them."""
    vapid = Vapid01()
    vapid.generate_keys()
    public = vapid.public_key.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    private = vapid.private_key.private_numbers().private_value.to_bytes(32, "big")
    return b64url(public), b64url(private)


def main() -> int:
    public, private = generate()
    print(f"VAPID_PUBLIC_KEY={public}")
    print(f"VAPID_PRIVATE_KEY={private}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
