"""Forced password change, dev-only demo accounts and Sign in with Google (ADR-0012)."""

from __future__ import annotations

import base64
import json
import time
import urllib.parse
import uuid
from typing import Any

import pytest
from sqlalchemy import select

from app.cli import create_demo_account
from app.core.config import get_settings
from app.core.security import sign_payload, verify_password
from app.models import AuditEvent, ExternalIdentity, User
from app.modules.identity import google
from tests.conftest import owner_session

PW = "correct horse battery"
TEMP = "temporary-Pa55word!"


def _email(prefix: str = "u") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def _demo(email: str | None = None, password: str = TEMP) -> str:
    email = email or _email("demo")
    create_demo_account.create(email, "Demo Person", "en", password)
    return email


def _login(client: Any, email: str, password: str) -> Any:
    return client.post("/auth/login", json={"email": email, "password": password})


# ------------------------------------------------------------------ forced password change


def test_demo_account_must_change_password_before_anything_else(client: Any) -> None:
    email = _demo()
    r = _login(client, email, TEMP)
    assert r.status_code == 200, r.text
    assert r.json()["must_change_password"] is True
    assert client.get("/auth/me").json()["must_change_password"] is True
    # the server refuses everything else — hiding it in the SPA is not the protection
    for method, path, body in [
        ("GET", "/trees", None),
        ("POST", "/trees", {"name": "Sneaky tree"}),
        ("PATCH", "/auth/me", {"display_name": "Changed"}),
        ("GET", "/auth/sessions", None),
        ("POST", "/auth/mfa/setup", None),
    ]:
        r = client.request(method, path, json=body)
        assert r.status_code == 403, (path, r.text)
        assert r.json()["error"]["code"] == "password_change_required"


def test_forced_change_rejects_reusing_the_temporary_password(client: Any) -> None:
    email = _demo()
    _login(client, email, TEMP)
    r = client.post("/auth/password", json={"current_password": TEMP, "new_password": TEMP})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "password_reused"
    assert client.get("/trees").status_code == 403


def test_changing_the_password_lifts_the_block(client: Any, make_client: Any) -> None:
    email = _demo()
    _login(client, email, TEMP)
    r = client.post("/auth/password", json={"current_password": TEMP, "new_password": PW})
    assert r.status_code == 200, r.text
    assert client.get("/auth/me").json()["must_change_password"] is False
    assert client.get("/trees").status_code == 200
    # the temporary password no longer works anywhere
    other = make_client()
    assert _login(other, email, TEMP).status_code == 401
    assert _login(other, email, PW).status_code == 200
    with owner_session() as db:
        ev = db.scalars(select(AuditEvent).where(AuditEvent.action == "user.password_changed")).all()
        assert ev and ev[-1].details == {"forced": True}


def test_logout_is_allowed_while_a_change_is_pending(client: Any) -> None:
    email = _demo()
    _login(client, email, TEMP)
    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401


def test_password_reset_clears_the_flag(client: Any) -> None:
    from tests.mail import latest_token

    email = _demo()
    client.post("/auth/password-reset/request", json={"email": email})
    token = latest_token(email, "password_reset")
    r = client.post("/auth/password-reset/confirm", json={"token": token, "new_password": PW})
    assert r.status_code == 200, r.text
    _login(client, email, PW)
    assert client.get("/auth/me").json()["must_change_password"] is False
    assert client.get("/trees").status_code == 200


def test_regular_accounts_are_unaffected(owner: Any) -> None:
    assert owner.get("/auth/me").json()["must_change_password"] is False
    assert owner.get("/trees").status_code == 200


# ------------------------------------------------------------------ demo account CLI


def test_demo_account_is_verified_hashed_and_flagged() -> None:
    email = _demo()
    with owner_session() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        assert user.email_verified_at is not None and user.must_change_password
        assert TEMP not in user.password_hash and verify_password(user.password_hash, TEMP)
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "user.demo_account_created"))


def test_demo_account_refused_outside_development_and_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "env", "production")
    with pytest.raises(RuntimeError):
        create_demo_account.create(_email(), "X", "en", TEMP)


def test_demo_account_refuses_existing_email_and_weak_password() -> None:
    email = _demo()
    with pytest.raises(ValueError, match="already exists"):
        create_demo_account.create(email, "X", "en", TEMP)
    with pytest.raises(ValueError):
        create_demo_account.create(_email(), "X", "en", "short")


def test_demo_cli_reads_password_only_from_env(monkeypatch: pytest.MonkeyPatch, capsys: Any) -> None:
    monkeypatch.delenv(create_demo_account.PASSWORD_ENV, raising=False)
    assert create_demo_account.main(["--email", _email(), "--name", "X"]) == 2
    monkeypatch.setenv(create_demo_account.PASSWORD_ENV, TEMP)
    assert create_demo_account.main(["--email", _email(), "--name", "X"]) == 0
    out = capsys.readouterr()
    assert TEMP not in out.out and TEMP not in out.err


# ------------------------------------------------------------------ Sign in with Google

CLIENT_ID = "test-client.apps.googleusercontent.com"


@pytest.fixture
def google_on(monkeypatch: pytest.MonkeyPatch) -> None:
    s = get_settings()
    monkeypatch.setattr(s, "google_client_id", CLIENT_ID)
    monkeypatch.setattr(s, "google_client_secret", "test-secret")


def _id_token(**claims: Any) -> str:
    def enc(d: dict[str, Any]) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()

    return f"{enc({'alg': 'RS256'})}.{enc(claims)}.c2ln"


def _claims(nonce: str, /, **over: Any) -> dict[str, Any]:
    now = int(time.time())
    base = {
        "iss": "https://accounts.google.com",
        "aud": CLIENT_ID,
        "sub": "g-" + uuid.uuid4().hex,
        "email": _email("g").replace("@example.com", "@gmail.com"),
        "email_verified": True,
        "name": "Manish Pandey",
        "iat": now,
        "exp": now + 3600,
        "nonce": nonce,
    }
    base.update(over)
    return base


def _start(client: Any, next_path: str = "/") -> tuple[str, str]:
    r = client.get(f"/auth/google/start?next={urllib.parse.quote(next_path)}", follow_redirects=False)
    assert r.status_code == 303, r.text
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(r.headers["location"]).query)
    assert q["code_challenge_method"] == ["S256"] and q["client_id"] == [CLIENT_ID]
    return q["state"][0], q["nonce"][0]


def _callback(
    client: Any, monkeypatch: pytest.MonkeyPatch, state: str, claims: dict[str, Any], code: str = "abc"
) -> Any:
    monkeypatch.setattr(google, "exchange_code", lambda c, v: {"id_token": _id_token(**claims)})
    return client.get(f"/auth/google/callback?code={code}&state={state}", follow_redirects=False)


def _error(r: Any) -> str | None:
    loc = r.headers.get("location", "")
    q = urllib.parse.parse_qs(urllib.parse.urlsplit(loc).query)
    return q.get("oauth_error", [None])[0]


def test_google_is_off_unless_configured(client: Any) -> None:
    assert client.get("/auth/providers").json() == {"google": False}
    assert client.get("/auth/google/start", follow_redirects=False).status_code == 404
    assert client.get("/auth/google/callback?code=x&state=y", follow_redirects=False).status_code == 404


def test_new_google_user_is_created_verified_and_signed_in(
    client: Any, google_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get("/auth/providers").json() == {"google": True}
    state, nonce = _start(client, "/trees/new")
    c = _claims(nonce)
    r = _callback(client, monkeypatch, state, c)
    assert r.status_code == 303 and r.headers["location"] == "/trees/new"
    me = client.get("/auth/me").json()
    assert me["email"] == c["email"] and me["email_verified"] and me["display_name"] == "Manish Pandey"
    with owner_session() as db:
        ident = db.scalar(select(ExternalIdentity).where(ExternalIdentity.subject == c["sub"]))
        assert ident is not None and ident.provider == "google"
        login = db.scalars(select(AuditEvent).where(AuditEvent.action == "user.login")).all()[-1]
        assert login.details == {"method": "google"}


def test_returning_google_user_matches_by_subject_not_email(
    make_client: Any, google_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = make_client()
    state, nonce = _start(first)
    c = _claims(nonce)
    _callback(first, monkeypatch, state, c)
    uid = first.get("/auth/me").json()["id"]
    again = make_client()
    state, nonce = _start(again)
    # same Google account, email changed at Google: still the same Vanshavali account
    _callback(again, monkeypatch, state, _claims(nonce, sub=c["sub"], email="renamed@gmail.com"))
    assert again.get("/auth/me").json()["id"] == uid


@pytest.mark.parametrize(
    ("over", "code"),
    [
        ({"aud": "someone-else"}, "oauth_failed"),
        ({"iss": "https://evil.example"}, "oauth_failed"),
        ({"exp": int(time.time()) - 5}, "oauth_failed"),
        ({"nonce": "wrong"}, "oauth_failed"),
        ({"email_verified": False}, "email_unverified"),
        ({"sub": ""}, "oauth_failed"),
    ],
)
def test_bad_id_tokens_are_refused(
    client: Any, google_on: None, monkeypatch: pytest.MonkeyPatch, over: dict[str, Any], code: str
) -> None:
    state, nonce = _start(client)
    r = _callback(client, monkeypatch, state, _claims(nonce, **over))
    assert r.status_code == 303 and _error(r) == code
    assert client.get("/auth/me").status_code == 401
    with owner_session() as db:
        assert db.scalar(select(ExternalIdentity)) is None


def test_state_must_match_this_browsers_cookie(
    make_client: Any, google_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    victim = make_client()
    attacker = make_client()
    a_state, a_nonce = _start(attacker)
    # login CSRF: the victim's browser is sent the attacker's callback URL
    r = _callback(victim, monkeypatch, a_state, _claims(a_nonce))
    assert _error(r) == "oauth_state"
    assert victim.get("/auth/me").status_code == 401
    # wrong state with the right cookie
    _, v_nonce = _start(victim)
    r = _callback(victim, monkeypatch, "not-the-state", _claims(v_nonce))
    assert _error(r) == "oauth_state"


def test_tampered_or_foreign_signed_state_is_refused(
    client: Any, google_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = google.callback_path()
    # a validly signed payload made for another purpose (e.g. a download token) is not a state cookie
    forged = sign_payload({"p": "download", "state": "s", "nonce": "n", "v": "v", "next": "/"}, 60)
    client.client.cookies.set(google.STATE_COOKIE, forged, path=path)
    r = _callback(client, monkeypatch, "s", _claims("n"))
    assert _error(r) == "oauth_state"
    good = sign_payload({"p": google.STATE_PURPOSE, "state": "s", "nonce": "n", "v": "v", "next": "/"}, 60)
    client.client.cookies.set(google.STATE_COOKIE, good[:-3] + "AAA", path=path)
    r = _callback(client, monkeypatch, "s", _claims("n"))
    assert _error(r) == "oauth_state"


def test_state_cookie_is_single_use(client: Any, google_on: None, monkeypatch: pytest.MonkeyPatch) -> None:
    state, nonce = _start(client)
    c = _claims(nonce)
    assert _callback(client, monkeypatch, state, c).headers["location"] == "/"
    client.post("/auth/logout")
    r = _callback(client, monkeypatch, state, c)
    assert _error(r) == "oauth_state"


@pytest.mark.parametrize(
    "bad", ["//evil.example/x", "https://evil.example", "/\\evil.example", "javascript:alert(1)"]
)
def test_next_cannot_redirect_off_site(
    client: Any, google_on: None, monkeypatch: pytest.MonkeyPatch, bad: str
) -> None:
    state, nonce = _start(client, bad)
    r = _callback(client, monkeypatch, state, _claims(nonce))
    assert r.headers["location"] == "/"


def test_existing_gmail_account_is_linked(
    owner: Any, make_client: Any, google_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = _email("linked").replace("@example.com", "@gmail.com")
    base = make_client()
    base.register(email=email)
    uid = base.get("/auth/me").json()["id"]
    g = make_client()
    state, nonce = _start(g)
    _callback(g, monkeypatch, state, _claims(nonce, email=email))
    assert g.get("/auth/me").json()["id"] == uid
    # the password still works too
    assert _login(make_client(), email, PW).status_code == 200


def test_non_google_address_needs_the_password_first(
    make_client: Any, google_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = _email("corp")  # @example.com: Google is not authoritative for it
    make_client().register(email=email)
    g = make_client()
    state, nonce = _start(g)
    r = _callback(g, monkeypatch, state, _claims(nonce, email=email))
    assert _error(r) == "link_requires_password"
    assert g.get("/auth/me").status_code == 401


def test_workspace_hosted_domain_may_link(
    make_client: Any, google_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = _email("ws")
    make_client().register(email=email)
    g = make_client()
    state, nonce = _start(g)
    _callback(g, monkeypatch, state, _claims(nonce, email=email, hd="example.com"))
    assert g.get("/auth/me").json()["email"] == email


def test_mfa_accounts_cannot_bypass_totp_with_google(
    make_client: Any, google_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import datetime as dt

    email = _email("mfa").replace("@example.com", "@gmail.com")
    make_client().register(email=email)
    with owner_session() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        user.mfa_enabled_at = dt.datetime.now(dt.UTC)
        db.commit()
    g = make_client()
    state, nonce = _start(g)
    r = _callback(g, monkeypatch, state, _claims(nonce, email=email))
    assert _error(r) == "mfa_enabled"
    assert g.get("/auth/me").status_code == 401


def test_pre_registration_squatter_loses_access_when_owner_signs_in_with_google(
    client: Any, make_client: Any, google_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    victim_email = _email("victim").replace("@example.com", "@gmail.com")
    # attacker registers the victim's address first (never verified)
    r = client.post(
        "/auth/register", json={"email": victim_email, "password": "attacker-password-1", "display_name": "X"}
    )
    assert r.status_code == 202
    g = make_client()
    state, nonce = _start(g)
    _callback(g, monkeypatch, state, _claims(nonce, email=victim_email))
    assert g.get("/auth/me").json()["email"] == victim_email
    # the squatter's password no longer signs in
    assert _login(make_client(), victim_email, "attacker-password-1").status_code == 401


def test_inactive_account_cannot_sign_in_with_google(
    make_client: Any, google_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = _email("gone").replace("@example.com", "@gmail.com")
    make_client().register(email=email)
    with owner_session() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        user.is_active = False
        db.commit()
    g = make_client()
    state, nonce = _start(g)
    assert _error(_callback(g, monkeypatch, state, _claims(nonce, email=email))) == "account_inactive"


def test_token_exchange_failure_creates_nothing(
    client: Any, google_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    state, _ = _start(client)

    def boom(code: str, verifier: str) -> dict[str, Any]:
        raise google.OidcError("oauth_failed", "network down")

    monkeypatch.setattr(google, "exchange_code", boom)
    r = client.get(f"/auth/google/callback?code=x&state={state}", follow_redirects=False)
    assert _error(r) == "oauth_failed"
    with owner_session() as db:
        assert db.scalar(select(ExternalIdentity)) is None
        failed = db.scalars(select(AuditEvent).where(AuditEvent.action == "user.oauth_failed")).all()
        assert failed and failed[-1].details == {"provider": "google", "reason": "oauth_failed"}


def test_forced_password_change_still_applies_after_google_sign_in(
    make_client: Any, google_on: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    email = _demo(_email("demo").replace("@example.com", "@gmail.com"))
    g = make_client()
    state, nonce = _start(g)
    _callback(g, monkeypatch, state, _claims(nonce, email=email))
    assert g.get("/auth/me").json()["must_change_password"] is True
    assert g.get("/trees").status_code == 403
