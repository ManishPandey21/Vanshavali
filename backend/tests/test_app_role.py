"""ensure_app_role on managed PostgreSQL (pilot drill, Oct 2026).

Managed instances run migrations as a schema owner without SUPERUSER (CREATEROLE only). The second
deploy failed there: re-asserting NOSUPERUSER on an existing role needs SUPERUSER. The role is now
created once with the safe attributes and afterwards only verified.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app.cli.ensure_app_role import UnsafeRole, ensure
from tests.conftest import _ADMIN_URL


@pytest.fixture
def managed_like() -> Iterator[tuple[str, str]]:
    """A database owned by a CREATEROLE, non-superuser owner (like a managed instance's owner role)."""
    tag = uuid.uuid4().hex[:8]
    owner, db, app_role = f"vsh_t_owner_{tag}", f"vsh_t_db_{tag}", f"vsh_t_app_{tag}"
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as c:
        c.exec_driver_sql(f"CREATE ROLE {owner} LOGIN CREATEROLE PASSWORD '{owner}'")
        c.exec_driver_sql(f"CREATE DATABASE {db} OWNER {owner}")
    url = (
        make_url(_ADMIN_URL)
        .set(username=owner, password=owner, database=db)
        .render_as_string(hide_password=False)
    )
    eng = create_engine(url, poolclass=NullPool)
    with eng.begin() as c:
        c.exec_driver_sql("CREATE TABLE person (id int)")
    try:
        yield url, app_role
    finally:
        eng.dispose()
        with admin.connect() as c:
            c.exec_driver_sql(f"DROP DATABASE IF EXISTS {db} WITH (FORCE)")
            c.exec_driver_sql(f"DROP ROLE IF EXISTS {app_role}")
            c.exec_driver_sql(f"DROP ROLE IF EXISTS {owner}")
        admin.dispose()


def test_repeated_deploys_with_a_non_superuser_owner(managed_like: tuple[str, str]) -> None:
    url, role = managed_like
    eng = create_engine(url, poolclass=NullPool)
    with eng.begin() as c:
        assert c.execute(text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")).scalar() is False
        assert ensure(c, role, "first-password") is False  # first deploy: created
    with eng.begin() as c:
        assert ensure(c, role, "rotated-password") is True  # every later deploy: failed before the fix
        flags = c.execute(
            text(
                "SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole, rolcanlogin FROM pg_roles WHERE rolname = :r"
            ),
            {"r": role},
        ).one()
    assert tuple(flags) == (False, False, False, False, True)
    # the new password works and the role has DML on the owner's tables, nothing more
    app = create_engine(make_url(url).set(username=role, password="rotated-password"), poolclass=NullPool)
    with app.begin() as c:
        c.exec_driver_sql("INSERT INTO person VALUES (1)")
        with pytest.raises(Exception, match=r"permission denied|must be owner"):
            c.exec_driver_sql("DROP TABLE person")
    app.dispose()
    eng.dispose()


def test_a_role_that_bypasses_rls_stops_the_release(managed_like: tuple[str, str]) -> None:
    url, role = managed_like
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    with admin.connect() as c:  # e.g. someone "fixed" a permission problem by hand
        c.exec_driver_sql(f"CREATE ROLE {role} LOGIN BYPASSRLS PASSWORD 'x'")
    admin.dispose()
    eng = create_engine(url, poolclass=NullPool)
    with eng.begin() as c, pytest.raises(UnsafeRole, match="BYPASSRLS"):
        ensure(c, role, "whatever")
    eng.dispose()
