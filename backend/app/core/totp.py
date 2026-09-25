"""RFC 6238 TOTP (SHA-1, 30 s, 6 digits) — compatible with common authenticator apps."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import struct
import time
from urllib.parse import quote


def new_secret() -> str:
    return base64.b32encode(os.urandom(20)).decode().rstrip("=")


def _code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def now_code(secret: str, at: float | None = None) -> str:
    return _code(secret, int((at if at is not None else time.time()) // 30))


def verify(secret: str, code: str, *, window: int = 1, at: float | None = None) -> bool:
    code = (code or "").strip().replace(" ", "")
    if len(code) != 6 or not code.isdigit():
        return False
    counter = int((at if at is not None else time.time()) // 30)
    return any(hmac.compare_digest(_code(secret, counter + d), code) for d in range(-window, window + 1))


def otpauth_uri(secret: str, account: str, issuer: str = "Vanshavali") -> str:
    return f"otpauth://totp/{quote(issuer)}:{quote(account)}?secret={secret}&issuer={quote(issuer)}&digits=6&period=30"
