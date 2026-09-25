"""Email verification, password reset and non-enumerating registration (ADR-0005, SEC-12)."""

from __future__ import annotations

import datetime as dt
import logging
import uuid

import pytest
from sqlalchemy import select, update

from app.core import mailer
from app.core.config import Settings
from app.core.db import get_sessionmaker
from app.core.security import token_hash
from app.models import AuditEvent, AuthToken, AuthTokenPurpose, User
from app.modules.identity import service as identity
from tests.conftest import join_tree
from tests.mail import all_mail, latest_mail, latest_token

PW = "correct horse battery"


def _email(prefix: str = "u") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def _register(client, email: str, **extra):  # type: ignore[no-untyped-def]
    body = {"email": email, "password": PW, "display_name": "Asha", **extra}
    return client.post("/auth/register", json=body)


def _expire(purpose: AuthTokenPurpose) -> None:
    with get_sessionmaker()() as db:
        db.execute(
            update(AuthToken)
            .where(AuthToken.purpose == purpose)
            .values(expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1))
        )
        db.commit()


# ------------------------------------------------------------------ registration + verification


def test_registration_is_generic_and_mails_the_right_thing(client, make_client, monkeypatch):
    client.register(email="taken@example.com")
    hashes = []
    real = identity.hash_password
    monkeypatch.setattr(identity, "hash_password", lambda p: hashes.append(p) or real(p))

    new_email = _email("new")
    taken = _register(make_client(), "Taken@Example.com")
    fresh = _register(make_client(), new_email)
    assert taken.status_code == fresh.status_code == 202
    assert taken.json() == fresh.json()
    assert "we've sent a link" in fresh.json()["message"]
    assert len(hashes) == 2  # the password is hashed on both paths (similar timing)
    assert "vsh_session" not in taken.cookies and "vsh_session" not in fresh.cookies

    assert latest_mail(new_email)["kind"] == "verify_email"
    notice = latest_mail("taken@example.com")
    assert notice["kind"] == "existing_account"
    assert "/verify-email/" not in notice["text"] and "/reset-password/" not in notice["text"]
    assert "/forgot-password" in notice["text"] and "/login" in notice["text"]
    # the existing account is untouched
    with get_sessionmaker()() as db:
        assert db.scalar(select(User.display_name).where(User.email == "taken@example.com")) == "Test User"


def test_unverified_login_refused_only_after_correct_password(make_client):
    email = _email()
    c = make_client()
    assert _register(c, email).status_code == 202
    assert c.get("/auth/me").status_code == 401
    wrong = c.post("/auth/login", json={"email": email, "password": "not the password"})
    assert wrong.status_code == 401 and wrong.json()["error"]["code"] == "invalid_credentials"
    right = c.post("/auth/login", json={"email": email, "password": PW})
    assert right.status_code == 403 and right.json()["error"]["code"] == "email_not_verified"
    assert "vsh_session" not in right.cookies


def test_verify_email_signs_in_and_token_is_single_use(make_client):
    email = _email()
    c = make_client()
    _register(c, email)
    token = latest_token(email, "verify_email")
    r = c.post("/auth/verify-email", json={"token": token})
    assert r.status_code == 200, r.text
    assert r.json()["email_verified"] is True and r.json()["email"] == email
    assert c.get("/auth/me").status_code == 200

    again = make_client().post("/auth/verify-email", json={"token": token})
    assert again.status_code == 400 and again.json()["error"]["code"] == "token_invalid"

    # stored only as a SHA-256 hash
    with get_sessionmaker()() as db:
        row = db.scalar(select(AuthToken))
        assert row.token_hash == token_hash(token) != token and row.used_at is not None
        audit = db.scalar(select(AuditEvent).where(AuditEvent.action == "user.email_verified"))
        assert audit is not None

    # and the password now signs in normally
    anon = make_client()
    assert anon.post("/auth/login", json={"email": email, "password": PW}).status_code == 200


def test_verify_link_expires(make_client):
    email = _email()
    c = make_client()
    _register(c, email)
    token = latest_token(email, "verify_email")
    _expire(AuthTokenPurpose.VERIFY_EMAIL)
    r = c.post("/auth/verify-email", json={"token": token})
    assert r.status_code == 400 and r.json()["error"]["code"] == "token_invalid"
    with get_sessionmaker()() as db:
        assert db.scalar(select(User.email_verified_at).where(User.email == email)) is None


def test_verify_ttl_is_48_hours_and_reset_1_hour(make_client):
    email = _email()
    _register(make_client(), email)
    make_client().post("/auth/password-reset/request", json={"email": email})
    with get_sessionmaker()() as db:
        rows = {r.purpose: r for r in db.scalars(select(AuthToken))}
    v, p = rows[AuthTokenPurpose.VERIFY_EMAIL], rows[AuthTokenPurpose.PASSWORD_RESET]
    assert dt.timedelta(hours=47) < v.expires_at - v.created_at <= dt.timedelta(hours=48, minutes=1)
    assert dt.timedelta(minutes=59) < p.expires_at - p.created_at <= dt.timedelta(minutes=61)


def test_garbage_and_wrong_purpose_tokens_rejected(make_client):
    email = _email()
    c = make_client()
    _register(c, email)
    verify = latest_token(email, "verify_email")
    r = c.post("/auth/password-reset/confirm", json={"token": verify, "new_password": "brand new password"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "token_invalid"
    r = c.post("/auth/verify-email", json={"token": "x" * 43})
    assert r.status_code == 400 and r.json()["error"]["code"] == "token_invalid"


def test_resend_verification_is_generic_and_replaces_old_link(client, make_client):
    client.register(email="verified@example.com")
    email = _email()
    _register(make_client(), email)
    first = latest_token(email, "verify_email")

    anon = make_client()
    before = len(all_mail())
    answers = [
        anon.post("/auth/resend-verification", json={"email": e})
        for e in (email, "verified@example.com", "nobody@example.com")
    ]
    assert {a.status_code for a in answers} == {202}
    assert len({a.text for a in answers}) == 1
    assert len(all_mail()) == before + 1  # only the unverified account got mail
    second = latest_token(email, "verify_email")
    assert second != first
    assert anon.post("/auth/verify-email", json={"token": first}).status_code == 400
    assert anon.post("/auth/verify-email", json={"token": second}).status_code == 200


def test_resend_verification_rate_limited(make_client):
    anon = make_client()
    codes = [
        anon.post("/auth/resend-verification", json={"email": "someone@example.com"}).status_code
        for _ in range(5)
    ]
    assert codes[:3] == [202, 202, 202] and 429 in codes


def test_registration_rate_limited_per_email(make_client):
    email = _email()
    codes = [_register(make_client(), email).status_code for _ in range(7)]
    assert codes[:5] == [202] * 5 and 429 in codes


def test_hindi_email_for_hindi_speakers(make_client):
    email = _email()
    _register(make_client(), email, preferred_language="hi")
    msg = latest_mail(email, "verify_email")
    assert "पुष्टि" in msg["subject"] and "नमस्ते" in msg["text"]
    assert "<img" not in msg["html"]  # no tracking pixels
    make_client().post("/auth/password-reset/request", json={"email": email})
    assert "रीसेट" in latest_mail(email, "password_reset")["subject"]


def test_registration_next_path_is_carried_and_validated(make_client):
    email = _email()
    assert _register(make_client(), email, next="/invite/abc123").status_code == 202
    assert "?next=/invite/abc123" in latest_mail(email)["text"]
    for bad in ("//evil.example", "https://evil.example", "/\\evil.example"):
        assert _register(make_client(), _email(), next=bad).status_code == 422


def test_invitation_requires_verified_email(owner, tree, make_client):
    member = make_client()
    member.register(email="joiner@example.com")
    # a session held by an account that is not verified is not honoured (defence in depth)
    with get_sessionmaker()() as db:
        db.execute(update(User).where(User.email == "joiner@example.com").values(email_verified_at=None))
        db.commit()
    assert member.get("/auth/me").status_code == 401
    with get_sessionmaker()() as db:
        db.execute(
            update(User)
            .where(User.email == "joiner@example.com")
            .values(email_verified_at=dt.datetime.now(dt.UTC))
        )
        db.commit()
    join_tree(owner, member, tree["id"], ["VIEWER"])


def test_accept_invitation_service_refuses_unverified_user():
    from app.authz.context import RequestInfo
    from app.core.errors import Forbidden
    from app.modules.trees import service as trees

    user = User(email="x@example.com", password_hash="x", display_name="X")
    with pytest.raises(Forbidden) as exc, get_sessionmaker()() as db:
        trees.accept_invitation(db, user, "whatever", RequestInfo(ip=None, user_agent=None))
    assert exc.value.code == "email_not_verified"


# ------------------------------------------------------------------------------ password reset


def test_reset_request_is_generic(client, make_client):
    client.register(email="has-account@example.com")
    anon = make_client()
    before = len(all_mail())
    known = anon.post("/auth/password-reset/request", json={"email": "Has-Account@example.com"})
    unknown = anon.post("/auth/password-reset/request", json={"email": "no-account@example.com"})
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()
    assert len(all_mail()) == before + 1
    assert latest_mail("has-account@example.com")["kind"] == "password_reset"


def test_reset_confirm_sets_password_revokes_sessions_and_is_single_use(client, make_client):
    client.register(email="reset@example.com")
    other_device = make_client()
    assert (
        other_device.post("/auth/login", json={"email": "reset@example.com", "password": PW}).status_code
        == 200
    )

    anon = make_client()
    anon.post("/auth/password-reset/request", json={"email": "reset@example.com"})
    token = latest_token("reset@example.com", "password_reset")
    r = anon.post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": "a brand new passphrase"}
    )
    assert r.status_code == 200, r.text

    # every session is gone
    assert client.get("/auth/me").status_code == 401
    assert other_device.get("/auth/me").status_code == 401
    # old password fails, new one works
    assert anon.post("/auth/login", json={"email": "reset@example.com", "password": PW}).status_code == 401
    ok = anon.post("/auth/login", json={"email": "reset@example.com", "password": "a brand new passphrase"})
    assert ok.status_code == 200
    # single use
    again = make_client().post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": "yet another passphrase"}
    )
    assert again.status_code == 400 and again.json()["error"]["code"] == "token_invalid"
    with get_sessionmaker()() as db:
        ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "user.password_reset"))
        assert ev is not None and ev.details["sessions_revoked"] >= 2


def test_reset_link_expires(client, make_client):
    client.register(email="exp@example.com")
    anon = make_client()
    anon.post("/auth/password-reset/request", json={"email": "exp@example.com"})
    token = latest_token("exp@example.com", "password_reset")
    _expire(AuthTokenPurpose.PASSWORD_RESET)
    r = anon.post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": "a brand new passphrase"}
    )
    assert r.status_code == 400 and r.json()["error"]["code"] == "token_invalid"


def test_reset_link_dies_when_password_changes(client, make_client):
    client.register(email="change@example.com")
    anon = make_client()
    anon.post("/auth/password-reset/request", json={"email": "change@example.com"})
    token = latest_token("change@example.com", "password_reset")
    r = client.post("/auth/password", json={"current_password": PW, "new_password": "changed it myself ok"})
    assert r.status_code == 200, r.text
    r = anon.post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": "a brand new passphrase"}
    )
    assert r.status_code == 400


def test_newer_reset_link_replaces_older(client, make_client):
    client.register(email="twice@example.com")
    anon = make_client()
    anon.post("/auth/password-reset/request", json={"email": "twice@example.com"})
    first = latest_token("twice@example.com", "password_reset")
    anon.post("/auth/password-reset/request", json={"email": "twice@example.com"})
    body = {"token": first, "new_password": "a brand new passphrase"}
    assert anon.post("/auth/password-reset/confirm", json=body).status_code == 400


def test_weak_reset_password_rejected_without_burning_token(client, make_client):
    client.register(email="weak@example.com")
    anon = make_client()
    anon.post("/auth/password-reset/request", json={"email": "weak@example.com"})
    token = latest_token("weak@example.com", "password_reset")
    r = anon.post("/auth/password-reset/confirm", json={"token": token, "new_password": "password123"})
    assert r.status_code == 422
    r = anon.post(
        "/auth/password-reset/confirm", json={"token": token, "new_password": "a brand new passphrase"}
    )
    assert r.status_code == 200


def test_reset_verifies_an_unverified_account(make_client):
    email = _email()
    anon = make_client()
    _register(anon, email)
    anon.post("/auth/password-reset/request", json={"email": email})
    token = latest_token(email, "password_reset")
    body = {"token": token, "new_password": "a brand new passphrase"}
    assert anon.post("/auth/password-reset/confirm", json=body).status_code == 200
    login = anon.post("/auth/login", json={"email": email, "password": "a brand new passphrase"})
    assert login.status_code == 200


def test_reset_not_sent_to_closed_account(client, make_client):
    client.register(email="closing@example.com")
    assert client.post("/auth/close-account", json={"password": PW}).status_code == 200
    before = len(all_mail())
    r = make_client().post("/auth/password-reset/request", json={"email": "closing@example.com"})
    assert r.status_code == 202 and len(all_mail()) == before


def test_reset_request_rate_limited_per_email_and_ip(make_client):
    anon = make_client()
    codes = [
        anon.post("/auth/password-reset/request", json={"email": "target@example.com"}).status_code
        for _ in range(7)
    ]
    assert codes[:5] == [202] * 5 and 429 in codes
    ip_codes = [
        anon.post("/auth/password-reset/request", json={"email": f"x{i}@example.com"}).status_code
        for i in range(10)
    ]
    assert 429 in ip_codes  # 10/min per IP (7 already used above)


def test_tokens_never_reach_the_audit_log(client, make_client):
    email = _email()
    anon = make_client()
    _register(anon, email)
    verify = latest_token(email, "verify_email")
    anon.post("/auth/verify-email", json={"token": verify})
    anon.post("/auth/password-reset/request", json={"email": email})
    reset = latest_token(email, "password_reset")
    anon.post("/auth/password-reset/confirm", json={"token": reset, "new_password": "a brand new passphrase"})
    with get_sessionmaker()() as db:
        events = db.scalars(select(AuditEvent)).all()
    actions = {e.action for e in events}
    assert {
        "user.registered",
        "user.email_verified",
        "user.password_reset_requested",
        "user.password_reset",
    } <= actions
    blob = " ".join(f"{e.summary} {e.details}" for e in events)
    for secret in (verify, reset, token_hash(verify), token_hash(reset)):
        assert secret not in blob


# ------------------------------------------------------------------------------------- mailer


def test_console_backend_redacts_tokens_outside_development(monkeypatch, caplog):
    monkeypatch.setattr(mailer, "get_settings", lambda: Settings(env="test", mail_backend="console"))
    token = "T" * 43
    with caplog.at_level(logging.INFO, logger="app.mail"):
        mailer.deliver(
            {
                "to": "asha@example.com",
                "subject": "s",
                "text": f"open http://x/verify-email/{token}",
                "html": "<p>x</p>",
                "sensitive": [token],
                "kind": "verify_email",
            }
        )
    assert token not in caplog.text and "[redacted]" in caplog.text
    assert "asha@example.com" not in caplog.text

    monkeypatch.setattr(mailer, "get_settings", lambda: Settings(env="development", mail_backend="console"))
    caplog.clear()
    with caplog.at_level(logging.INFO, logger="app.mail"):
        mailer.deliver(
            {
                "to": "a@example.com",
                "subject": "s",
                "text": f"/verify-email/{token}",
                "html": "",
                "sensitive": [token],
            }
        )
    assert token in caplog.text  # developers can click the link locally


def test_redact_catches_token_like_segments():
    assert mailer.redact("secret abc here", ["abc"]) == "secret [redacted] here"
    out = mailer.redact("see https://h/reset-password/" + "a" * 43 + "?next=" + "b" * 40)
    assert "a" * 43 not in out and "b" * 40 not in out


def test_eml_file_has_text_and_html_parts(make_client):
    from pathlib import Path

    from app.core.config import get_settings

    email = _email()
    _register(make_client(), email)
    emls = sorted(Path(get_settings().mail_file_dir).glob("*.eml"))
    raw = emls[-1].read_text()
    assert "text/plain" in raw and "text/html" in raw and email in raw


@pytest.mark.parametrize("backend", ["console", "file"])
def test_production_refuses_non_smtp_mail(backend):
    with pytest.raises(ValueError, match="VSH_MAIL_BACKEND"):
        Settings(
            env="production",
            mail_backend=backend,
            scanner="clamd",
            standard_data_key="c3RhbmRhcmQta2V5LTMyLWJ5dGVzLXByb2QtLS0tLS0=",
            vault_data_key="dmF1bHQta2V5LTMyLWJ5dGVzLXByb2R1Y3Rpb24tLS0=",
            signing_key="prod-signing",
            cookie_secure=True,
        )


def test_smtp_backend_uses_starttls(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):  # type: ignore[no-untyped-def]
            sent["host"], sent["port"] = host, port

        def __enter__(self):  # type: ignore[no-untyped-def]
            return self

        def __exit__(self, *a):  # type: ignore[no-untyped-def]
            return False

        def ehlo(self):  # type: ignore[no-untyped-def]
            pass

        def starttls(self, context):  # type: ignore[no-untyped-def]
            sent["tls"] = True

        def login(self, user, pw):  # type: ignore[no-untyped-def]
            sent["user"] = user

        def send_message(self, msg):  # type: ignore[no-untyped-def]
            sent["to"] = msg["To"]

    s = Settings(mail_backend="smtp", smtp_host="smtp.example", smtp_user="u", smtp_password="p")
    monkeypatch.setattr(mailer, "get_settings", lambda: s)
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    mailer.deliver({"to": "a@example.com", "subject": "s", "text": "t", "html": "<p>t</p>"})
    assert sent == {"host": "smtp.example", "port": 587, "tls": True, "user": "u", "to": "a@example.com"}
