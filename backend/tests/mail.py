"""Read emails written by the ``file`` mail backend (VSH_MAIL_BACKEND=file) in tests."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from app.core.config import get_settings

_LINK_RE = re.compile(r"/(verify-email|reset-password)/([A-Za-z0-9_-]{20,})")


def all_mail(to: str | None = None) -> list[dict[str, Any]]:
    """Every message (oldest first), optionally only those addressed to ``to``."""
    out = []
    for f in sorted(Path(get_settings().mail_file_dir).glob("*.json")):
        m = json.loads(f.read_text(encoding="utf-8"))
        if to is None or m["to"].lower() == to.lower():
            out.append(m)
    return out


def latest_mail(to: str, kind: str | None = None) -> dict[str, Any]:
    msgs = [m for m in all_mail(to) if kind is None or m["kind"] == kind]
    assert msgs, f"no {kind or ''} email for {to}"
    return msgs[-1]


def token_from(message: dict[str, Any]) -> str:
    match = _LINK_RE.search(message["text"])
    assert match, "no token link in email"
    return match.group(2)


def latest_token(to: str, kind: str) -> str:
    return token_from(latest_mail(to, kind))
