"""Sign in with Google: OpenID Connect authorization code + PKCE, run by the backend (ADR-0012)."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz.context import RequestInfo
from app.core import audit
from app.core.config import get_settings
from app.core.security import hash_password, new_token, sign_payload, verify_signed
from app.models import ExternalIdentity, User
from app.modules.identity import service

PROVIDER = "google"
STATE_COOKIE = "vsh_oidc"
STATE_PURPOSE = "oidc_google"
ISSUERS = ("https://accounts.google.com", "accounts.google.com")
AUTHORITATIVE_DOMAINS = ("gmail.com", "googlemail.com")
MAX_IAT_SKEW_SECONDS = 600
TOKEN_TIMEOUT_SECONDS = 10


class OidcError(Exception):
    """A failed sign-in. ``code`` is short and safe to put in the redirect URL."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(detail or code)
        self.code = code


def callback_path() -> str:
    s = get_settings()
    return f"{s.api_prefix}/auth/google/callback"


def safe_next(next_path: str | None) -> str:
    """Same-origin path only (mirrors the SPA's ``safeNext``): no scheme, host, ``//`` or backslash."""
    if not next_path or not next_path.startswith("/") or next_path.startswith("//"):
        return "/"
    if any(c == "\\" or ord(c) < 0x20 or ord(c) == 0x7F for c in next_path):
        return "/"
    parts = urllib.parse.urlsplit(next_path)
    if parts.scheme or parts.netloc:
        return "/"
    return next_path


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def begin(next_path: str | None) -> tuple[str, str]:
    """Return (Google authorize URL, signed state cookie value)."""
    s = get_settings()
    state = new_token()
    nonce = new_token()
    verifier = _b64url(secrets.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    cookie = sign_payload(
        {"p": STATE_PURPOSE, "state": state, "nonce": nonce, "v": verifier, "next": safe_next(next_path)},
        s.oidc_state_ttl_seconds,
    )
    query = urllib.parse.urlencode(
        {
            "client_id": s.google_client_id,
            "redirect_uri": s.google_callback_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "prompt": "select_account",
        }
    )
    return f"{s.google_authorize_url}?{query}", cookie


def read_state(cookie: str | None, state: str | None) -> dict[str, Any]:
    """Validate the signed state cookie against the ``state`` Google sent back."""
    if not cookie or not state:
        raise OidcError("oauth_state", "missing state cookie or parameter")
    body = verify_signed(cookie)
    if body is None or body.get("p") != STATE_PURPOSE:
        raise OidcError("oauth_state", "state cookie invalid or expired")
    if not secrets.compare_digest(str(body.get("state", "")), state):
        raise OidcError("oauth_state", "state mismatch")
    return body


def exchange_code(code: str, verifier: str) -> dict[str, Any]:
    """Swap the authorization code for tokens at Google's token endpoint (back channel, TLS)."""
    s = get_settings()
    data = urllib.parse.urlencode(
        {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": s.google_client_id,
            "client_secret": s.google_client_secret,
            "redirect_uri": s.google_callback_uri,
            "code_verifier": verifier,
        }
    ).encode()
    if not s.google_token_url.startswith("https://"):
        raise OidcError("oauth_failed", "token endpoint must be https")
    req = urllib.request.Request(  # noqa: S310 - https enforced above
        s.google_token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=TOKEN_TIMEOUT_SECONDS) as resp:  # noqa: S310
            payload: dict[str, Any] = json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise OidcError("oauth_failed", f"token exchange failed: {type(e).__name__}") from e
    return payload


def _decode_id_token(id_token: str) -> dict[str, Any]:
    try:
        _, payload, _ = id_token.split(".")
        claims: dict[str, Any] = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, json.JSONDecodeError) as e:
        raise OidcError("oauth_failed", "malformed id_token") from e
    return claims


@dataclass(frozen=True)
class GoogleClaims:
    subject: str
    email: str
    email_verified: bool
    hosted_domain: str | None
    name: str | None
    locale: str | None


def validate_id_token(token_response: dict[str, Any], nonce: str, now: float | None = None) -> GoogleClaims:
    """Check iss, aud, exp/iat and nonce of an ID token received from the token endpoint.

    The signature is not re-checked: the token came straight from Google over TLS in the back
    channel, which OIDC Core §3.1.3.7(6) accepts in place of signature validation (ADR-0012).
    """
    id_token = token_response.get("id_token")
    if not isinstance(id_token, str):
        raise OidcError("oauth_failed", "no id_token in token response")
    c = _decode_id_token(id_token)
    now = time.time() if now is None else now
    s = get_settings()
    if c.get("iss") not in ISSUERS:
        raise OidcError("oauth_failed", "unexpected issuer")
    aud = c.get("aud")
    if aud != s.google_client_id and not (isinstance(aud, list) and s.google_client_id in aud):
        raise OidcError("oauth_failed", "audience mismatch")
    if isinstance(aud, list) and c.get("azp") != s.google_client_id:
        raise OidcError("oauth_failed", "authorized party mismatch")
    try:
        exp, iat = float(c["exp"]), float(c["iat"])
    except (KeyError, TypeError, ValueError) as e:
        raise OidcError("oauth_failed", "missing exp/iat") from e
    if (
        exp <= now
        or iat > now + MAX_IAT_SKEW_SECONDS
        or iat < now - s.oidc_state_ttl_seconds - MAX_IAT_SKEW_SECONDS
    ):
        raise OidcError("oauth_failed", "token expired or not yet valid")
    if not secrets.compare_digest(str(c.get("nonce", "")), nonce):
        raise OidcError("oauth_failed", "nonce mismatch")
    sub, email = c.get("sub"), c.get("email")
    if not isinstance(sub, str) or not sub or not isinstance(email, str) or "@" not in email:
        raise OidcError("oauth_failed", "missing sub or email")
    verified = c.get("email_verified") in (True, "true")
    hd = c.get("hd") if isinstance(c.get("hd"), str) else None
    return GoogleClaims(
        subject=sub,
        email=service.normalise_email(email),
        email_verified=verified,
        hosted_domain=hd,
        name=c.get("name") if isinstance(c.get("name"), str) else None,
        locale=c.get("locale") if isinstance(c.get("locale"), str) else None,
    )


def _google_is_authoritative(claims: GoogleClaims) -> bool:
    domain = claims.email.rsplit("@", 1)[1]
    return domain in AUTHORITATIVE_DOMAINS or (claims.hosted_domain or "").lower() == domain


def resolve_user(db: Session, claims: GoogleClaims, info: RequestInfo) -> User:
    """Find, link or create the account for a validated Google identity (ADR-0012 rules)."""
    if not claims.email_verified:
        raise OidcError("email_unverified")
    now = dt.datetime.now(dt.UTC)
    ident = db.scalar(
        select(ExternalIdentity).where(
            ExternalIdentity.provider == PROVIDER, ExternalIdentity.subject == claims.subject
        )
    )
    if ident is not None:
        user = db.get(User, ident.user_id)
        if user is None or not user.is_active:
            raise OidcError("account_inactive")
        if user.mfa_enabled_at is not None:
            raise OidcError("mfa_enabled")
        ident.last_used_at = now
        return user

    user = db.scalar(select(User).where(User.email == claims.email))
    if user is not None:
        if not user.is_active:
            raise OidcError("account_inactive")
        if not _google_is_authoritative(claims):
            raise OidcError("link_requires_password")
        if user.mfa_enabled_at is not None:
            raise OidcError("mfa_enabled")
        if user.email_verified_at is None:
            # Someone may have pre-registered this address: take their password and sessions away.
            user.email_verified_at = now
            user.password_hash = hash_password(new_token())
            user.password_changed_at = now
            service.revoke_all(db, user.id)
            service.invalidate_tokens(db, user.id)
        _link(db, user, claims, info, now)
        return user

    user = User(
        email=claims.email,
        password_hash=hash_password(new_token()),  # unusable; "Forgot password" can set a real one
        display_name=(claims.name or claims.email.split("@", 1)[0]).strip()[:200],
        preferred_language="hi" if (claims.locale or "").lower().startswith("hi") else "en",
        email_verified_at=now,
    )
    db.add(user)
    db.flush()
    audit.record(
        db,
        action="user.registered",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        details={"method": PROVIDER},
        ip=info.ip,
        user_agent=info.user_agent,
    )
    _link(db, user, claims, info, now)
    return user


def _link(db: Session, user: User, claims: GoogleClaims, info: RequestInfo, now: dt.datetime) -> None:
    db.add(
        ExternalIdentity(
            user_id=user.id,
            provider=PROVIDER,
            subject=claims.subject,
            email_at_link=claims.email,
            last_used_at=now,
        )
    )
    db.flush()
    audit.record(
        db,
        action="user.external_identity_linked",
        actor_user_id=user.id,
        target_type="user",
        target_id=user.id,
        details={"provider": PROVIDER},
        ip=info.ip,
        user_agent=info.user_agent,
    )
