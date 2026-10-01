"""Client IP behind reverse proxies (DAST finding, Oct 2026).

The per-IP rate limits, audit log and session list all use the client address uvicorn derives from
X-Forwarded-For. With ``--forwarded-allow-ips "*"`` the *leftmost* entry won, and nginx appends to
whatever the client sent, so any client could pick its own IP and dodge the login throttle. Trust
is now limited to the proxies in front of the API (FORWARDED_ALLOW_IPS).
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import pytest
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

NGINX = "172.28.0.10"  # the compose nginx container (docker-compose.yml)
SPOOFED = "203.0.113.66"  # what an attacker puts in X-Forwarded-For
REAL = "198.51.100.7"  # what nginx appends: the address it actually saw


def _client_ip(trusted: str, peer: str, xff: str | None) -> str:
    seen: dict[str, Any] = {}

    async def app(scope: dict[str, Any], receive: Any, send: Any) -> None:
        seen["client"] = scope["client"][0]

    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    scope = {"type": "http", "client": (peer, 50000), "headers": headers, "scheme": "http"}
    asyncio.run(ProxyHeadersMiddleware(app, trusted_hosts=trusted)(scope, None, None))
    return str(seen["client"])


def test_spoofed_leftmost_forwarded_for_is_ignored_from_a_trusted_proxy():
    # nginx forwards "<whatever the client sent>, <real peer>": the real peer must win
    assert _client_ip(NGINX, NGINX, f"{SPOOFED}, {REAL}") == REAL


def test_forwarded_for_from_an_untrusted_peer_is_ignored():
    # e.g. someone reaching the API port directly
    assert _client_ip(NGINX, REAL, SPOOFED) == REAL


def test_load_balancer_hop_is_skipped_when_trusted():
    lb = "10.0.5.4"
    assert _client_ip(f"{NGINX},10.0.5.0/24", NGINX, f"{SPOOFED}, {REAL}, {lb}") == REAL


def test_wildcard_trust_is_exactly_the_bug():
    """Documents why "*" must never be configured: the attacker-chosen address wins."""
    assert _client_ip("*", NGINX, f"{SPOOFED}, {REAL}") == SPOOFED


@pytest.mark.parametrize("path", ["backend/Dockerfile", "docker-compose.yml", ".github/workflows/dast.yml"])
def test_shipped_configuration_never_trusts_every_proxy(path: str):
    root = Path(__file__).resolve().parents[2]
    text = (root / path).read_text()
    assert not re.search(r"forwarded-allow-ips\W+\*|FORWARDED_ALLOW_IPS\W+[\"']?\*", text), path
