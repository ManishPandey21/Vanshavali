"""Test harness: a dedicated PostgreSQL database per worker, tables truncated between tests.

The schema is created by the *owner* (admin) connection, while the application under test connects
as a separate non-owner role (``vsh_app_test``) — exactly like production — so PostgreSQL row-level
security is really enforced in every API test. Tests that need raw database access (fixtures,
assertions on stored state) use ``owner_session()``, which bypasses RLS as the table owner does.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from collections.abc import Iterator
from typing import Any

import pytest

_DB_NAME = os.environ.get("VSH_TEST_DB_NAME", "vanshavali_test")
_ADMIN_URL = os.environ.get(
    "VSH_TEST_ADMIN_URL", "postgresql+psycopg://vanshavali:vanshavali@localhost:5432/postgres"
)
_BASE = _ADMIN_URL.rsplit("/", 1)[0]
APP_ROLE = os.environ.get("VSH_TEST_APP_ROLE", "vsh_app_test")
OWNER_URL = f"{_BASE}/{_DB_NAME}"
from sqlalchemy.engine import make_url  # noqa: E402

_APP_URL = make_url(OWNER_URL).set(username=APP_ROLE, password=APP_ROLE).render_as_string(hide_password=False)
os.environ["VSH_ENV"] = "test"
os.environ["VSH_DATABASE_URL"] = _APP_URL
os.environ.setdefault("VSH_STORAGE_LOCAL_PATH", tempfile.mkdtemp(prefix="vsh-test-storage-"))
os.environ["VSH_JOB_MODE"] = "sync"
os.environ["VSH_RATE_LIMIT_BACKEND"] = "memory"
os.environ["VSH_SCANNER"] = "eicar_test"
os.environ["VSH_MAIL_BACKEND"] = "file"  # tests read tokens from tests/mail.py
os.environ.setdefault("VSH_MAIL_FILE_DIR", tempfile.mkdtemp(prefix="vsh-test-mail-"))

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.db import get_engine  # noqa: E402
from app.core.ratelimit import get_limiter  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import Base  # noqa: E402

EXTENSIONS = ("pg_trgm", "unaccent")


_owner_engine = create_engine(OWNER_URL, pool_pre_ping=True)
_OwnerSession = sessionmaker(bind=_owner_engine, expire_on_commit=False)


def owner_session() -> Session:
    """Raw DB access as the table owner (not subject to row-level security). Test fixtures only."""
    return _OwnerSession()


def _recreate_database() -> None:
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{_DB_NAME}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{_DB_NAME}"'))
        exists = c.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": APP_ROLE}).first()
        if not exists:
            c.execute(text(f"CREATE ROLE {APP_ROLE} LOGIN PASSWORD '{APP_ROLE}' NOSUPERUSER NOBYPASSRLS"))
    admin.dispose()


@pytest.fixture(scope="session", autouse=True)
def _database() -> Iterator[None]:
    from app.models.rls import GRANT_APP_ROLE_SQL

    _recreate_database()
    with _owner_engine.begin() as c:
        for ext in EXTENSIONS:
            c.execute(text(f"CREATE EXTENSION IF NOT EXISTS {ext}"))
    Base.metadata.create_all(_owner_engine)
    with _owner_engine.begin() as c:
        c.execute(text(GRANT_APP_ROLE_SQL.format(role=APP_ROLE)))
    yield
    get_engine().dispose()
    _owner_engine.dispose()


# A fixed instant in the middle of a minute and of an hour, so rate-limit windows never roll over
# during a test (the limiter's fixed windows follow the clock; see app/core/ratelimit.py).
PINNED_NOW = 1_800_000_030.0


@pytest.fixture(autouse=True)
def _pinned_rate_limit_clock() -> Iterator[None]:
    """Every test sees one fixed rate-limit window and fresh counters, whatever the wall clock."""
    limiter = get_limiter()
    limiter.reset()
    original = limiter.clock
    limiter.clock = lambda: PINNED_NOW
    yield
    limiter.clock = original


@pytest.fixture(autouse=True)
def _clean_tables() -> Iterator[None]:
    yield
    names = ", ".join(f'"{t.name}"' for t in Base.metadata.sorted_tables)
    with _owner_engine.begin() as c:
        c.execute(text(f"TRUNCATE {names} RESTART IDENTITY CASCADE"))
    get_limiter().reset()  # type: ignore[union-attr]


@pytest.fixture(scope="session")
def app() -> Any:
    return create_app()


class ApiClient:
    """TestClient wrapper that sends the CSRF header like the real frontend does."""

    def __init__(self, app: Any) -> None:
        self.client = TestClient(app, base_url="http://testserver")
        self.prefix = get_settings().api_prefix
        self.user: dict[str, Any] | None = None

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(extra or {})
        csrf = self.client.cookies.get(get_settings().csrf_cookie_name)
        if csrf:
            headers.setdefault(get_settings().csrf_header_name, csrf)
        return headers

    def _url(self, path: str) -> str:
        return path if path.startswith("http") or path.startswith(self.prefix) else f"{self.prefix}{path}"

    def request(self, method: str, path: str, **kw: Any) -> Any:
        kw["headers"] = self._headers(kw.get("headers"))
        return self.client.request(method, self._url(path), **kw)

    def get(self, path: str, **kw: Any) -> Any:
        return self.request("GET", path, **kw)

    def post(self, path: str, **kw: Any) -> Any:
        return self.request("POST", path, **kw)

    def patch(self, path: str, **kw: Any) -> Any:
        return self.request("PATCH", path, **kw)

    def put(self, path: str, **kw: Any) -> Any:
        return self.request("PUT", path, **kw)

    def delete(self, path: str, **kw: Any) -> Any:
        return self.request("DELETE", path, **kw)

    def register(
        self, email: str | None = None, password: str = "correct horse battery", name: str = "Test User"
    ) -> dict[str, Any]:
        email = email or f"user-{uuid.uuid4().hex[:8]}@example.com"
        r = self.post("/auth/register", json={"email": email, "password": password, "display_name": name})
        assert r.status_code == 202, r.text
        # registration signs nobody in: open the emailed verification link, which starts the session
        from tests.mail import latest_token

        r = self.post("/auth/verify-email", json={"token": latest_token(email.lower(), "verify_email")})
        assert r.status_code == 200, r.text
        self.user = r.json()
        self.user["password"] = password
        return self.user


@pytest.fixture
def make_client(app: Any):  # type: ignore[no-untyped-def]
    def _make() -> ApiClient:
        return ApiClient(app)

    return _make


@pytest.fixture
def client(make_client: Any) -> ApiClient:
    return make_client()


@pytest.fixture
def owner(make_client: Any) -> ApiClient:
    c = make_client()
    c.register(name="Tree Owner")
    return c


def attest(client: ApiClient, tree_id: str, language: str = "en") -> dict[str, Any]:
    """Confirm the family-data statement (ADR-0011) so ``client`` may add people to the tree."""
    stmt = client.get(f"/consent-statements/family_data?lang={language}").json()
    r = client.post(
        f"/trees/{tree_id}/attestation", json={"statement_version": stmt["version"], "language": language}
    )
    assert r.status_code == 201, r.text
    return r.json()


def new_tree(client: ApiClient, name: str) -> dict[str, Any]:
    """Create a tree and confirm the family-data statement for it."""
    r = client.post("/trees", json={"name": name})
    assert r.status_code == 201, r.text
    attest(client, r.json()["id"])
    return r.json()


@pytest.fixture
def tree(owner: ApiClient) -> dict[str, Any]:
    return new_tree(owner, "Iyer Family")


def join_tree(
    owner: ApiClient,
    member: ApiClient,
    tree_id: str,
    roles: list[str],
    branch_id: str | None = None,
    *,
    attested: bool = True,
) -> dict[str, Any]:
    """Invite ``member`` with ``roles`` and accept; returns the membership tree payload.

    By default the member also confirms the family-data statement, as the UI asks before adding people.
    """
    assert member.user is not None
    body: dict[str, Any] = {"email": member.user["email"], "roles": roles}
    if branch_id:
        body["branch_id"] = branch_id
    r = owner.post(f"/trees/{tree_id}/invitations", json=body)
    assert r.status_code == 201, r.text
    r2 = member.post(f"/invitations/{r.json()['token']}/accept")
    assert r2.status_code == 200, r2.text
    if attested:
        attest(member, tree_id)
    return r2.json()


@pytest.fixture
def member_factory(make_client: Any, owner: ApiClient, tree: dict[str, Any]):  # type: ignore[no-untyped-def]
    def _make(roles: list[str], branch_id: str | None = None, name: str = "Member") -> ApiClient:
        c = make_client()
        c.register(name=name)
        join_tree(owner, c, tree["id"], roles, branch_id)
        return c

    return _make
