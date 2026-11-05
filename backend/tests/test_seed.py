"""Dev/test seed command: demo owner + tree, platform system admin (no tree access), guards."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import func, select

from app.cli import seed_demo
from app.cli.seed_demo import seed, seed_superadmin
from app.core.config import get_settings
from app.core.security import verify_password
from app.models import AuditEvent, TreeMembership, User
from tests.conftest import owner_session

DEMO_PW = "demo-seed-Pa55word"
ADMIN_PW = "admin-seed-Pa55word"


def _email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"


def _user(email: str) -> User:
    with owner_session() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        return user


def _count(email: str) -> int:
    with owner_session() as db:
        return int(db.scalar(select(func.count()).select_from(User).where(User.email == email)) or 0)


def _login(client: Any, email: str, password: str) -> Any:
    return client.post("/auth/login", json={"email": email, "password": password})


@pytest.fixture
def seed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(seed_demo.DEMO_PASSWORD_ENV, DEMO_PW)
    monkeypatch.setenv(seed_demo.SUPERADMIN_PASSWORD_ENV, ADMIN_PW)


def test_seed_demo_loads_and_is_idempotent(client):
    tree_id = seed("seed@example.com", "seed-password-123")
    assert seed("seed@example.com", "seed-password-123") == tree_id
    r = client.post("/auth/login", json={"email": "seed@example.com", "password": "seed-password-123"})
    assert r.status_code == 200
    people = client.get(f"/trees/{tree_id}/people?limit=50").json()["items"]
    assert len(people) == 10
    arjun = next(p for p in people if p["display_name"] == "Arjun Iyer")
    assert arjun["is_minor"] is True
    kavya = next(p for p in people if p["display_name"] == "Kavya Iyer")
    fam = client.get(f"/trees/{tree_id}/people/{kavya['id']}/family").json()
    assert fam["parents"][0]["relationship_type"] == "adoptive_parent"


def test_cli_creates_both_accounts_with_the_right_roles(seed_env, make_client):
    assert seed_demo.main([]) == 0

    demo = _user(seed_demo.DEMO_EMAIL)
    admin = _user(seed_demo.SUPERADMIN_EMAIL)
    assert demo.email_verified_at is not None and not demo.is_system_admin and not demo.must_change_password
    assert admin.email_verified_at is not None and admin.is_system_admin and admin.must_change_password
    assert verify_password(admin.password_hash, ADMIN_PW) and ADMIN_PW not in admin.password_hash
    with owner_session() as db:
        # the demo user owns the demo tree; the system admin is a member of no tree (ADR-0006, T12)
        roles = db.scalars(select(TreeMembership.roles).where(TreeMembership.user_id == demo.id)).all()
        assert roles == [["OWNER"]]
        assert db.scalar(select(func.count()).where(TreeMembership.user_id == admin.id)) == 0
        assert db.scalar(
            select(AuditEvent).where(
                AuditEvent.action == "user.system_admin_seeded", AuditEvent.target_id == admin.id
            )
        )

    d = make_client()
    assert _login(d, seed_demo.DEMO_EMAIL, DEMO_PW).status_code == 200
    demo_trees = d.get("/trees").json()
    assert [t["name"] for t in demo_trees] == ["Iyer Family (demo)"]

    a = make_client()
    r = _login(a, seed_demo.SUPERADMIN_EMAIL, ADMIN_PW)
    assert r.status_code == 200, r.text
    assert r.json()["must_change_password"] is True


def test_system_admin_gets_no_tree_access(seed_env, make_client):
    assert seed_demo.main([]) == 0
    d = make_client()
    _login(d, seed_demo.DEMO_EMAIL, DEMO_PW)
    tree_id = d.get("/trees").json()[0]["id"]

    a = make_client()
    _login(a, seed_demo.SUPERADMIN_EMAIL, ADMIN_PW)
    r = a.post("/auth/password", json={"current_password": ADMIN_PW, "new_password": "fresh-admin-Pa55word"})
    assert r.status_code == 200, r.text
    assert a.get("/trees").json() == []
    assert a.get(f"/trees/{tree_id}").status_code == 404
    assert a.get(f"/trees/{tree_id}/people?limit=5").status_code == 404


def test_cli_is_idempotent_and_never_resets_passwords(seed_env, monkeypatch):
    assert seed_demo.main([]) == 0
    before = (_user(seed_demo.DEMO_EMAIL).password_hash, _user(seed_demo.SUPERADMIN_EMAIL).password_hash)
    monkeypatch.setenv(seed_demo.DEMO_PASSWORD_ENV, "another-demo-Pa55word")
    monkeypatch.setenv(seed_demo.SUPERADMIN_PASSWORD_ENV, "another-admin-Pa55word")
    assert seed_demo.main([]) == 0
    assert seed_demo.main([]) == 0
    assert _count(seed_demo.DEMO_EMAIL) == 1 and _count(seed_demo.SUPERADMIN_EMAIL) == 1
    after = (_user(seed_demo.DEMO_EMAIL).password_hash, _user(seed_demo.SUPERADMIN_EMAIL).password_hash)
    assert before == after
    with owner_session() as db:
        demo_id = _user(seed_demo.DEMO_EMAIL).id
        assert db.scalar(select(func.count()).where(TreeMembership.user_id == demo_id)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(AuditEvent)
                .where(AuditEvent.action == "user.system_admin_seeded")
            )
            == 1
        )


def test_existing_ordinary_account_is_never_promoted(owner):
    email = owner.user["email"]
    with pytest.raises(ValueError, match="refusing to promote"):
        seed_superadmin(email, ADMIN_PW)
    assert not _user(email).is_system_admin


def test_admin_cannot_be_the_demo_tree_owner(seed_env):
    email = _email("admin")
    seed_superadmin(email, ADMIN_PW)
    with pytest.raises(ValueError, match="system admin"):
        seed(email, DEMO_PW)
    assert seed_demo.main(["--email", "Same@Example.com", "--admin-email", "same@example.com"]) == 1


@pytest.mark.parametrize("env", ["production"])
def test_refused_outside_development_and_test(env, seed_env, monkeypatch, capsys):
    monkeypatch.setattr(get_settings(), "env", env)
    assert seed_demo.main([]) == 2
    assert "only allowed when VSH_ENV is development or test" in capsys.readouterr().err
    with pytest.raises(seed_demo.SeedRefused):
        seed_superadmin(_email("admin"), ADMIN_PW)
    with pytest.raises(seed_demo.SeedRefused):
        seed(_email("demo"), DEMO_PW)
    assert _count(seed_demo.DEMO_EMAIL) == 0 and _count(seed_demo.SUPERADMIN_EMAIL) == 0


def test_passwords_come_only_from_the_environment(monkeypatch, capsys):
    monkeypatch.delenv(seed_demo.DEMO_PASSWORD_ENV, raising=False)
    monkeypatch.delenv(seed_demo.SUPERADMIN_PASSWORD_ENV, raising=False)
    assert seed_demo.main([]) == 2
    assert "VSH_DEMO_PASSWORD and VSH_SUPERADMIN_PASSWORD" in capsys.readouterr().err
    assert _count(seed_demo.DEMO_EMAIL) == 0 and _count(seed_demo.SUPERADMIN_EMAIL) == 0
    with pytest.raises(SystemExit):  # no --password option any more
        seed_demo.main(["--password", "x"])


def test_weak_seed_passwords_rejected_and_never_printed(seed_env, monkeypatch, capsys):
    monkeypatch.setenv(seed_demo.SUPERADMIN_PASSWORD_ENV, "short")
    assert seed_demo.main([]) == 1
    assert "VSH_SUPERADMIN_PASSWORD" in capsys.readouterr().err
    assert _count(seed_demo.SUPERADMIN_EMAIL) == 0 and _count(seed_demo.DEMO_EMAIL) == 0  # nothing written
    monkeypatch.setenv(seed_demo.SUPERADMIN_PASSWORD_ENV, ADMIN_PW)
    assert seed_demo.main([]) == 0
    out = capsys.readouterr()
    for pw in (DEMO_PW, ADMIN_PW):
        assert pw not in out.out and pw not in out.err
