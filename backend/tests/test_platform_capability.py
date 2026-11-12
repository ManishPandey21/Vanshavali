"""Platform capability, session-level two-step sign-in and the console gate (ADR-0028 §7, §8).

Negative tests first: the console is invisible without the capability, a capability is useless
without a fresh two-step session, writes need a step-up, the application role cannot grant itself a
capability, and a holder gets no family-tree access.
"""

from __future__ import annotations

import ast
import datetime as dt
import re
import uuid
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select, text, update

from app.authz import platform
from app.cli import platform as platform_cli
from app.core import totp
from app.core.config import get_settings
from app.core.db import get_engine
from app.main import create_app
from app.models import AuditEvent, PlatformCapability, PlatformCapabilityGrant, User, UserSession
from app.models.base import TreeScopedMixin
from app.models.rls import READ_ONLY_TABLES
from app.modules.platform import service
from app.modules.platform.service import GrantRefused
from tests.conftest import ApiClient, owner_session
from tests.test_account_security import _callback, _claims, _start
from tests.test_account_security import google_on as google_on  # re-exported pytest fixture
from tests.test_route_isolation import _tree_routes

MDA = PlatformCapability.MASTER_DATA_ADMIN
PASSWORD = "correct horse battery"
SESSION = "/admin/master-data/session"


# ------------------------------------------------------------------ helpers
@pytest.fixture
def console_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "masterdata_console_enabled", True)


def _email(prefix: str = "asha") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def enrol_mfa(client: ApiClient) -> str:
    secret: str = client.post("/auth/mfa/setup").json()["secret"]
    r = client.post("/auth/mfa/enable", json={"code": totp.now_code(secret)})
    assert r.status_code == 200, r.text
    return secret


def sign_in(make_client: Any, email: str, secret: str) -> ApiClient:
    c: ApiClient = make_client()
    r = c.post("/auth/login", json={"email": email, "password": PASSWORD, "mfa_code": totp.now_code(secret)})
    assert r.status_code == 200, r.text
    c.user = r.json()
    return c


def grant(email: str) -> None:
    with owner_session() as db:
        service.grant(
            db,
            email=email,
            capability=MDA,
            holder_name="Asha Rao",
            reason="pilot curation",
            operator="Ravi (ops)",
        )
        db.commit()


def holder(make_client: Any) -> tuple[ApiClient, str, str]:
    """An account with two-step sign-in and the capability, signed in with password + TOTP."""
    email = _email()
    first: ApiClient = make_client()
    first.register(email=email, name="Asha Rao")
    secret = enrol_mfa(first)
    grant(email)
    return sign_in(make_client, email, secret), email, secret


def console_routes() -> list[tuple[str, str]]:
    spec = create_app().openapi()
    out = []
    for path, ops in spec["paths"].items():
        if path.startswith("/api/v1/admin/master-data"):
            out += [(m.upper(), path) for m in ops if m in ("get", "post", "put", "patch", "delete")]
    return out


def hit_all(c: ApiClient) -> set[int]:
    codes = set()
    for method, path in console_routes():
        url = re.sub(r"\{[a-z_]+\}", str(uuid.uuid4()), path.replace("/api/v1", ""))
        codes.add(
            c.request(method, url, **({"json": {}} if method in ("POST", "PUT", "PATCH") else {})).status_code
        )
    return codes


def set_session(email: str, **values: Any) -> None:
    with owner_session() as db:
        uid = db.scalar(select(User.id).where(User.email == email))
        db.execute(update(UserSession).where(UserSession.user_id == uid).values(**values))
        db.commit()


def now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# ------------------------------------------------------------------ who gets in
def test_console_routes_exist_and_are_hidden_from_everyone_without_the_capability(
    console_on: None, make_client: Any
) -> None:
    assert console_routes(), "no console routes registered"
    ordinary: ApiClient = make_client()
    ordinary.register()
    assert hit_all(ordinary) == {404}
    # two-step sign-in alone is not a capability
    email = _email("plain")
    first: ApiClient = make_client()
    first.register(email=email)
    assert hit_all(sign_in(make_client, email, enrol_mfa(first))) == {404}
    # nor is the old system-admin flag
    with owner_session() as db:
        db.execute(update(User).where(User.email == email).values(is_system_admin=True))
        db.commit()
    assert hit_all(sign_in(make_client, email, first_secret(email))) == {404}
    anon: ApiClient = make_client()
    assert hit_all(anon) == {401}


def first_secret(email: str) -> str:
    from app.modules.identity.service import mfa_secret

    with owner_session() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        return mfa_secret(user)


def test_console_is_off_by_default_even_for_a_holder(make_client: Any) -> None:
    c, _, _ = holder(make_client)
    assert get_settings().masterdata_console_enabled is False
    assert c.get(SESSION).status_code == 404
    assert c.get("/auth/me").json()["platform_capabilities"] == []


def test_holder_on_a_fresh_two_step_session_gets_in(console_on: None, make_client: Any) -> None:
    c, _, _ = holder(make_client)
    r = c.get(SESSION)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["capabilities"] == ["master_data.admin"] and body["step_up_valid_until"] is None
    assert c.get("/auth/me").json()["platform_capabilities"] == ["master_data.admin"]
    other: ApiClient = make_client()
    other.register()
    assert other.get("/auth/me").json()["platform_capabilities"] == []


def test_a_session_opened_without_totp_never_qualifies(console_on: None, make_client: Any) -> None:
    email = _email()
    c: ApiClient = make_client()
    c.register(email=email)  # this session came from the email link
    secret = enrol_mfa(c)  # turning two-step on inside it does not make it a two-step session
    grant(email)
    r = c.get(SESSION)
    assert r.status_code == 403 and r.json()["error"]["code"] == "admin_mfa_required"
    # and a step-up does not upgrade it either
    assert c.post("/auth/step-up", json={"code": totp.now_code(secret)}).status_code == 200
    assert c.get(SESSION).json()["error"]["code"] == "admin_mfa_required"
    assert sign_in(make_client, email, secret).get(SESSION).status_code == 200


def test_a_two_step_session_expires_after_twelve_hours(console_on: None, make_client: Any) -> None:
    c, email, _ = holder(make_client)
    with owner_session() as db:  # two-step was turned on well before the session opened
        db.execute(
            update(User).where(User.email == email).values(mfa_enabled_at=now() - dt.timedelta(days=2))
        )
        db.commit()
    set_session(email, mfa_verified_at=now() - dt.timedelta(hours=11))
    assert c.get(SESSION).status_code == 200
    set_session(email, mfa_verified_at=now() - dt.timedelta(hours=12, minutes=1))
    r = c.get(SESSION)
    assert r.status_code == 403 and r.json()["error"]["code"] == "admin_mfa_required"


def test_turning_two_step_off_and_on_again_disqualifies_older_sessions(
    console_on: None, make_client: Any
) -> None:
    c, email, secret = holder(make_client)
    other = sign_in(make_client, email, secret)
    r = other.post("/auth/mfa/disable", json={"password": PASSWORD, "code": totp.now_code(secret)})
    assert r.status_code == 200, r.text
    assert c.get(SESSION).json()["error"]["code"] == "admin_mfa_required"  # checked on every request
    new_secret = enrol_mfa(other)  # a new secret, from a session that predates it
    for stale in (c, other):
        assert stale.get(SESSION).json()["error"]["code"] == "admin_mfa_required"
    assert sign_in(make_client, email, new_secret).get(SESSION).status_code == 200


def test_a_revoked_grant_loses_access_on_the_next_request(console_on: None, make_client: Any) -> None:
    c, email, _ = holder(make_client)
    assert c.get(SESSION).status_code == 200
    with owner_session() as db:
        service.revoke(db, email=email, capability=MDA, reason="left the project", operator="Ravi (ops)")
        db.commit()
    assert c.get(SESSION).status_code == 404


def test_a_closed_account_loses_the_capability(console_on: None, make_client: Any) -> None:
    _, email, _ = holder(make_client)
    with owner_session() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None and platform.capabilities(db, user) == {MDA}
        user.is_active = False
        assert platform.capabilities(db, user) == frozenset()


def test_google_sessions_never_count_as_two_step(
    console_on: None, google_on: None, make_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    c: ApiClient = make_client()
    state, nonce = _start(c)
    claims = _claims(nonce)
    assert _callback(c, monkeypatch, state, claims).status_code == 303
    enrol_mfa(c)
    grant(claims["email"])
    with owner_session() as db:
        uid = db.scalar(select(User.id).where(User.email == claims["email"]))
        sessions = db.scalars(select(UserSession).where(UserSession.user_id == uid)).all()
        assert sessions and all(s.mfa_verified_at is None for s in sessions)
    assert c.get(SESSION).json()["error"]["code"] == "admin_mfa_required"


def test_password_change_signs_out_the_holders_other_sessions(console_on: None, make_client: Any) -> None:
    c, email, secret = holder(make_client)
    other = sign_in(make_client, email, secret)
    r = other.post(
        "/auth/password", json={"current_password": PASSWORD, "new_password": "a much newer passphrase"}
    )
    assert r.status_code == 200, r.text
    assert c.get(SESSION).status_code == 401


# ------------------------------------------------------------------ step-up
def test_step_up_needs_the_right_code_and_is_audited(console_on: None, make_client: Any) -> None:
    c, _, secret = holder(make_client)
    wrong = "000000" if totp.now_code(secret) != "000000" else "111111"
    r = c.post("/auth/step-up", json={"code": wrong})
    assert r.status_code == 400 and r.json()["error"]["code"] == "mfa_invalid"
    assert c.get("/auth/me").status_code == 200  # still signed in
    r = c.post("/auth/step-up", json={"code": totp.now_code(secret)})
    assert r.status_code == 200, r.text
    until = dt.datetime.fromisoformat(r.json()["step_up_valid_until"])
    assert dt.timedelta(minutes=14) < until - now() <= dt.timedelta(minutes=15)
    assert c.get(SESSION).json()["step_up_valid_until"] is not None
    with owner_session() as db:
        actions = [e.action for e in db.scalars(select(AuditEvent).order_by(AuditEvent.created_at))]
        failed = db.scalars(select(AuditEvent).where(AuditEvent.action == "user.mfa_failed")).all()
    assert "user.mfa_step_up" in actions and any(e.details == {"step_up": True} for e in failed)


def test_step_up_needs_csrf_two_step_and_is_rate_limited(make_client: Any) -> None:
    plain: ApiClient = make_client()
    plain.register()
    r = plain.post("/auth/step-up", json={"code": "123456"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "mfa_not_enabled"
    c, _, secret = holder(make_client)
    r = c.client.post("/api/v1/auth/step-up", json={"code": totp.now_code(secret)})  # no CSRF header
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"
    wrong = "000000" if totp.now_code(secret) != "000000" else "111111"
    statuses = [c.post("/auth/step-up", json={"code": wrong}).status_code for _ in range(12)]
    assert statuses[-1] == 429


def test_writes_need_a_recent_step_up(console_on: None, make_client: Any) -> None:
    _, email, _ = holder(make_client)
    with owner_session() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        sess = db.scalars(select(UserSession).where(UserSession.user_id == user.id)).all()[-1]
        platform.require_platform(db, user, sess, MDA, write=False)
        for step_up in (None, now() - dt.timedelta(minutes=16)):
            sess.mfa_step_up_at = step_up
            with pytest.raises(Exception) as e:
                platform.require_platform(db, user, sess, MDA, write=True)
            assert getattr(e.value, "code", None) == "admin_step_up_required"
        sess.mfa_step_up_at = now() - dt.timedelta(minutes=14)
        platform.require_platform(db, user, sess, MDA, write=True)
        # someone else's session never counts
        stranger = UserSession(user_id=uuid.uuid4(), mfa_verified_at=now(), mfa_step_up_at=now())
        with pytest.raises(Exception) as e:
            platform.require_platform(db, user, stranger, MDA, write=True)
        assert getattr(e.value, "code", None) == "admin_mfa_required"
        db.rollback()


# ------------------------------------------------------------------ grants
def test_the_application_role_cannot_grant_itself_a_capability(make_client: Any) -> None:
    assert "platform_capability_grant" in READ_ONLY_TABLES
    _, email, _ = holder(make_client)
    with get_engine().connect() as c:  # the application's own (non-owner) role
        assert c.execute(text("SELECT count(*) FROM platform_capability_grant")).scalar() == 1
        uid = c.execute(text("SELECT id FROM app_user WHERE email = :e"), {"e": email}).scalar()
        for stmt in (
            "INSERT INTO platform_capability_grant (id, user_id, capability, holder_name, reason, granted_by) "
            f"VALUES (gen_random_uuid(), '{uid}', 'master_data.admin', 'x', 'x', 'x')",
            "UPDATE platform_capability_grant SET revoked_at = now()",
            "DELETE FROM platform_capability_grant",
            "TRUNCATE platform_capability_grant",
        ):
            with pytest.raises(Exception, match="permission denied"):
                c.execute(text(stmt))
            c.rollback()


def test_the_cli_refuses_without_the_owner_connection(make_client: Any, capsys: Any) -> None:
    email = _email()
    first: ApiClient = make_client()
    first.register(email=email)
    enrol_mfa(first)
    code = platform_cli.main(
        [
            "grant",
            email,
            "--capability",
            MDA.value,
            "--name",
            "Asha Rao",
            "--reason",
            "x",
            "--operator",
            "Ravi",
        ]
    )
    assert code == 2 and "permission denied" in capsys.readouterr().err
    assert platform_cli.main(["list"]) == 0  # reading is allowed


def test_only_named_verified_two_step_accounts_can_hold_a_capability(make_client: Any) -> None:
    def try_grant(email: str, **over: str) -> None:
        kw = {"holder_name": "Asha Rao", "reason": "pilot curation", "operator": "Ravi (ops)", **over}
        with owner_session() as db:
            service.grant(db, email=email, capability=MDA, **kw)
            db.commit()

    for role in ("admin@example.com", "Ops+pilot@example.com", "support@example.org"):
        with pytest.raises(GrantRefused, match="role or shared mailboxes"):
            try_grant(role)
    with pytest.raises(GrantRefused, match="no account"):
        try_grant(_email())
    unverified = _email()
    r = make_client().post(
        "/auth/register", json={"email": unverified, "password": PASSWORD, "display_name": "U"}
    )
    assert r.status_code == 202
    with pytest.raises(GrantRefused, match="not verified"):
        try_grant(unverified)
    no_mfa: ApiClient = make_client()
    no_mfa_email = _email()
    no_mfa.register(email=no_mfa_email)
    with pytest.raises(GrantRefused, match="two-step"):
        try_grant(no_mfa_email)
    enrol_mfa(no_mfa)
    with pytest.raises(GrantRefused, match="name"):
        try_grant(no_mfa_email, holder_name="  ")
    try_grant(no_mfa_email)
    with pytest.raises(GrantRefused, match="already holds"):
        try_grant(no_mfa_email)


def test_grants_and_revocations_are_audited_without_any_tree(make_client: Any) -> None:
    _, email, _ = holder(make_client)
    with owner_session() as db:
        service.revoke(db, email=email, capability=MDA, reason="rotation", operator="Ravi (ops)")
        db.commit()
        with pytest.raises(GrantRefused, match="does not hold"):
            service.revoke(db, email=email, capability=MDA, reason="again", operator="Ravi (ops)")
        events = db.scalars(select(AuditEvent).where(AuditEvent.action.like("platform.%"))).all()
        assert sorted(e.action for e in events) == [
            "platform.capability_granted",
            "platform.capability_revoked",
        ]
        assert all(e.tree_id is None and e.actor_user_id is None for e in events)
        assert all("Asha" not in str(e.details) for e in events)  # the holder's name stays in the grant row
        rows = db.scalars(select(PlatformCapabilityGrant)).all()
        assert len(rows) == 1 and rows[0].revoked_at is not None and rows[0].revoke_reason == "rotation"
        assert service.list_grants(db) == [] and len(service.list_grants(db, include_revoked=True)) == 1
    # a revoked holder can be granted again (the partial unique index covers active grants only)
    grant(email)


# ------------------------------------------------------------------ no tree access
def test_a_capability_holder_gets_no_tree_access(
    console_on: None, make_client: Any, tree: dict[str, Any]
) -> None:
    c, _, _ = holder(make_client)
    failures = []
    for method, path in _tree_routes():
        url = re.sub(
            r"\{[a-z_]+\}", str(uuid.uuid4()), path.replace("/api/v1", "").replace("{tree_id}", tree["id"])
        )
        r = c.request(method, url, **({"json": {}} if method in ("POST", "PUT", "PATCH") else {}))
        if r.status_code not in (404, 422):
            failures.append((method, path, r.status_code))
    assert failures == []


ROOT = Path(__file__).resolve().parents[1]
CONSOLE_MODULES = [
    ROOT / "app" / "authz" / "platform.py",
    *sorted((ROOT / "app" / "modules" / "platform").glob("*.py")),
]
ALLOWED_APP_MODULES = {"platform", "identity"}


def test_console_code_never_imports_tree_data() -> None:
    import app.models as models

    problems = []
    for path in CONSOLE_MODULES:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                mod = node.module
                if mod.startswith("app.modules."):
                    if mod.split(".")[2] not in ALLOWED_APP_MODULES:
                        problems.append(f"{path.name}: imports {mod}")
                if mod == "app.authz.context" or mod.startswith("app.authz.permissions"):
                    problems.append(f"{path.name}: imports tree authorisation ({mod})")
                if mod.startswith("app.models"):
                    for alias in node.names:
                        obj = getattr(models, alias.name, None)
                        if isinstance(obj, type) and issubclass(obj, TreeScopedMixin):
                            problems.append(f"{path.name}: imports tree-scoped model {alias.name}")
            if isinstance(node, ast.Name | ast.Attribute):
                name = node.id if isinstance(node, ast.Name) else node.attr
                if name in ("bind_tree", "load_tree_context"):
                    problems.append(f"{path.name}: uses {name}")
    assert problems == []
    assert len(CONSOLE_MODULES) >= 4
