from __future__ import annotations

from sqlalchemy import select

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.core.ratelimit import get_limiter
from app.models import AuditEvent, User, UserSession


def test_register_login_logout_flow(client):
    user = client.register(email="Asha@Example.com")
    assert user["email"] == "asha@example.com"
    me = client.get("/auth/me")
    assert me.status_code == 200 and me.json()["email"] == "asha@example.com"

    assert client.post("/auth/logout").status_code == 200
    assert client.get("/auth/me").status_code == 401

    r = client.post("/auth/login", json={"email": "asha@example.com", "password": "correct horse battery"})
    assert r.status_code == 200
    assert client.get("/auth/me").status_code == 200


def test_password_hash_is_argon2_and_session_token_not_stored_raw(client):
    client.register(email="hash@example.com")
    token = client.client.cookies.get("vsh_session")
    with get_sessionmaker()() as db:
        user = db.scalar(select(User).where(User.email == "hash@example.com"))
        assert user.password_hash.startswith("$argon2id$")
        tokens = db.scalars(select(UserSession.token_hash)).all()
        assert token not in tokens and len(tokens[0]) == 64


def test_duplicate_email_does_not_create_or_sign_in(client, make_client):
    client.register(email="dup@example.com")
    other = make_client()
    r = other.post(
        "/auth/register",
        json={"email": "dup@example.com", "password": "another long pw", "display_name": "X"},
    )
    # generic answer (SEC-12); nobody is signed in and the original password still works
    assert r.status_code == 202
    assert other.get("/auth/me").status_code == 401
    anon = make_client()
    ok = anon.post("/auth/login", json={"email": "dup@example.com", "password": "correct horse battery"})
    assert ok.status_code == 200


def test_weak_password_rejected(client):
    r = client.post(
        "/auth/register", json={"email": "w@example.com", "password": "password123", "display_name": "W"}
    )
    assert r.status_code == 422


def test_login_failure_is_generic_and_audited(client, make_client):
    client.register(email="gen@example.com")
    anon = make_client()
    bad_pw = anon.post("/auth/login", json={"email": "gen@example.com", "password": "wrong password!!"})
    no_user = anon.post("/auth/login", json={"email": "nobody@example.com", "password": "wrong password!!"})
    assert bad_pw.status_code == no_user.status_code == 401
    assert bad_pw.json()["error"]["message"] == no_user.json()["error"]["message"]
    with get_sessionmaker()() as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "user.login_failed")) is not None


def test_login_rate_limited(client, make_client):
    client.register(email="rl@example.com")
    anon = make_client()
    responses = [
        anon.post("/auth/login", json={"email": "rl@example.com", "password": "wrong password!!"})
        for _ in range(12)
    ]
    # the rate-limit clock is pinned (conftest), so all 12 fall in one window: exactly the configured
    # 10 attempts per email are answered, then every further attempt is refused
    assert [r.status_code for r in responses] == [401] * 10 + [429] * 2
    assert responses[-1].json()["error"]["code"] == "rate_limited"


def test_registration_rate_limited_per_ip(make_client, monkeypatch):
    # the per-IP registration limit is a setting (default 20/minute; E2E raises it) and is enforced
    monkeypatch.setattr(get_settings(), "register_rate_limit_per_minute", 3)
    anon = make_client()
    responses = [
        anon.post(
            "/auth/register",
            json={"email": f"burst{i}@example.com", "password": "correct horse battery", "display_name": "B"},
        )
        for i in range(5)
    ]
    assert [r.status_code for r in responses] == [202] * 3 + [429] * 2
    assert responses[-1].json()["error"]["code"] == "rate_limited"


def _token_uses(anon, n: int) -> list[int]:  # type: ignore[no-untyped-def]
    # every token use from one IP counts, valid or not, and both token flows share one bucket
    codes = []
    for i in range(n):
        if i % 2:
            r = anon.post(
                "/auth/password-reset/confirm", json={"token": "x" * 43, "new_password": "brand new password"}
            )
        else:
            r = anon.post("/auth/verify-email", json={"token": "x" * 43})
        codes.append(r.status_code)
    return codes


def test_token_use_rate_limited_per_ip_by_default(make_client):
    # production default: 30 token uses per minute per IP; the 31st is refused
    assert get_settings().token_rate_limit_per_minute == 30
    anon = make_client()
    codes = _token_uses(anon, 32)
    assert codes == [400] * 30 + [429] * 2
    r = anon.post("/auth/verify-email", json={"token": "x" * 43})
    assert r.status_code == 429
    assert r.json()["error"]["code"] == "rate_limited"


def test_token_rate_limit_is_a_setting(make_client, monkeypatch):
    # E2E raises it (VSH_TOKEN_RATE_LIMIT_PER_MINUTE); the setting moves the threshold both ways
    monkeypatch.setattr(get_settings(), "token_rate_limit_per_minute", 3)
    assert _token_uses(make_client(), 5) == [400] * 3 + [429] * 2
    get_limiter().reset()  # type: ignore[union-attr]
    monkeypatch.setattr(get_settings(), "token_rate_limit_per_minute", 40)
    assert _token_uses(make_client(), 41) == [400] * 40 + [429]


def test_csrf_required_for_unsafe_methods(client):
    client.register()
    # bypass the wrapper: no X-CSRF-Token header
    r = client.client.post("/api/v1/trees", json={"name": "No CSRF"})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"
    r = client.client.post("/api/v1/trees", json={"name": "Bad CSRF"}, headers={"X-CSRF-Token": "forged"})
    assert r.status_code == 403


def test_unauthenticated_requests_rejected(client):
    assert client.get("/trees").status_code == 401


def test_password_change_revokes_other_sessions(make_client):
    a = make_client()
    a.register(email="multi@example.com", password="first password here")
    b = make_client()
    assert (
        b.post(
            "/auth/login", json={"email": "multi@example.com", "password": "first password here"}
        ).status_code
        == 200
    )
    r = a.post(
        "/auth/password",
        json={"current_password": "first password here", "new_password": "second password here"},
    )
    assert r.status_code == 200
    assert a.get("/auth/me").status_code == 200
    assert b.get("/trees").status_code == 401


def test_revoke_other_sessions(make_client):
    a = make_client()
    a.register(email="rev@example.com")
    b = make_client()
    b.post("/auth/login", json={"email": "rev@example.com", "password": "correct horse battery"})
    assert len(a.get("/auth/sessions").json()) == 2
    assert a.post("/auth/sessions/revoke-others").status_code == 200
    assert b.get("/trees").status_code == 401
    assert a.get("/trees").status_code == 200


def test_security_headers_present(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["cache-control"] == "no-store"


def test_totp_mfa_enrolment_and_login(client, make_client):
    from app.core import totp

    client.register(email="mfa@example.com")
    setup = client.post("/auth/mfa/setup").json()
    secret = setup["secret"]
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    assert client.post("/auth/mfa/enable", json={"code": "000000"}).status_code == 400
    r = client.post("/auth/mfa/enable", json={"code": totp.now_code(secret)})
    assert r.status_code == 200 and r.json()["mfa_enabled"] is True

    other = make_client()
    creds = {"email": "mfa@example.com", "password": "correct horse battery"}
    r = other.post("/auth/login", json=creds)
    assert r.status_code == 401 and r.json()["error"]["code"] == "mfa_required"
    r = other.post(
        "/auth/login", json={**creds, "mfa_code": "123456" if totp.now_code(secret) != "123456" else "654321"}
    )
    assert r.json()["error"]["code"] == "mfa_invalid"
    r = other.post("/auth/login", json={**creds, "mfa_code": totp.now_code(secret)})
    assert r.status_code == 200
    # secret is stored encrypted
    from sqlalchemy import select

    from app.core.db import get_sessionmaker
    from app.models import User

    with get_sessionmaker()() as db:
        u = db.scalar(select(User).where(User.email == "mfa@example.com"))
        assert secret not in (u.mfa_secret_enc or "")


def test_totp_rfc6238_vector():
    import base64

    from app.core import totp

    secret = base64.b32encode(b"12345678901234567890").decode()
    assert totp.now_code(secret, at=59) == "287082"
    assert totp.now_code(secret, at=1111111109) == "081804"
