"""Version-stable encrypted JSON envelope for sensitive relational columns.

Migrations may import this module. Keep existing envelope decoding backwards compatible; introduce
a new named codec rather than changing the current format in place.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from app.core.storage import decrypt, encrypt


def encrypt_json(value: object, aad: str) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    return base64.b64encode(encrypt(raw, "VAULT", aad)).decode()


def decrypt_json(value: str, aad: str) -> Any:
    return json.loads(decrypt(base64.b64decode(value), aad).decode())
