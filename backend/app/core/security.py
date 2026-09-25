"""Password hashing, opaque tokens and HMAC-signed short-lived tokens."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from typing import Any

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import get_settings

_hasher = PasswordHasher()  # Argon2id with library defaults (ADR-0005)

_COMMON_PASSWORDS = {
    "password",
    "password123",
    "1234567890",
    "12345678910",
    "qwertyuiop",
    "iloveyou123",
    "letmein123",
    "welcome123",
    "admin12345",
    "passw0rd123",
}


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# Used to equalise timing when the user does not exist (no user enumeration).
DUMMY_HASH = _hasher.hash("vanshavali-dummy-password")


def password_problems(password: str) -> list[str]:
    problems = []
    if len(password) < 10:
        problems.append("Password must be at least 10 characters long")
    if password.lower() in _COMMON_PASSWORDS:
        problems.append("Password is too common")
    return problems


def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def sign_payload(payload: dict[str, Any], ttl_seconds: int) -> str:
    body = dict(payload, exp=int(time.time()) + ttl_seconds)
    raw = _b64(json.dumps(body, separators=(",", ":"), sort_keys=True).encode())
    sig = hmac.new(get_settings().signing_key.encode(), raw.encode(), hashlib.sha256).digest()
    return f"{raw}.{_b64(sig)}"


def verify_signed(token: str) -> dict[str, Any] | None:
    try:
        raw, sig = token.split(".", 1)
    except ValueError:
        return None
    expected = hmac.new(get_settings().signing_key.encode(), raw.encode(), hashlib.sha256).digest()
    try:
        if not hmac.compare_digest(expected, _unb64(sig)):
            return None
        body: dict[str, Any] = json.loads(_unb64(raw))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(body.get("exp", 0)) < int(time.time()):
        return None
    return body
