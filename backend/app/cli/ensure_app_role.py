"""Create (if missing) the non-owner application database role and grant it DML rights.

Usage (as the schema owner, after ``alembic upgrade head``):
    VSH_DATABASE_URL=<owner url> VSH_APP_DB_ROLE=vanshavali_app VSH_APP_DB_PASSWORD=... \
        python -m app.cli.ensure_app_role

The API and workers must connect as this role: it is not the table owner, has no BYPASSRLS, and is
therefore subject to the row-level security policies (ADR-0002). Idempotent; safe on every deploy.
"""

from __future__ import annotations

import os
import re
import sys

from sqlalchemy import Connection, text

from app.core.db import get_engine
from app.models.rls import GRANT_APP_ROLE_SQL

_ROLE_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


class UnsafeRole(Exception):
    pass


def _verify(conn: Connection, role: str) -> None:
    flags = conn.execute(
        text("SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = :r"),
        {"r": role},
    ).one()
    names = ("SUPERUSER", "BYPASSRLS", "CREATEDB", "CREATEROLE")
    unsafe = [name for name, on in zip(names, flags, strict=True) if on]
    if unsafe:
        raise UnsafeRole(
            f"role {role} has {', '.join(unsafe)}: the API would bypass row-level security. "
            f"A superuser must run: ALTER ROLE {role} NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE"
        )
    owner = conn.execute(
        text("SELECT 1 FROM pg_tables WHERE schemaname = 'public' AND tableowner = :r LIMIT 1"), {"r": role}
    ).scalar()
    if owner:
        raise UnsafeRole(f"role {role} owns tables: the application must not connect as the schema owner")


def ensure(conn: Connection, role: str, password: str) -> bool:
    """Create the role or update its password; then prove it cannot bypass RLS. True if it existed.

    Managed PostgreSQL runs migrations as a schema owner that is NOT a superuser (it has CREATEROLE).
    Such an owner may create a role with the NO* attributes and may later change its password, but
    may not touch SUPERUSER (or CREATEDB/BYPASSRLS, unless it holds them itself). Re-asserting the
    attributes on every deploy therefore failed from the second deploy on (pilot drill, Oct 2026);
    instead the attributes are verified, and an unsafe role stops the release.
    """
    exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).scalar()
    if exists:
        _verify(conn, role)  # before touching it: an unsafe role gets the clear message below
    # Role names cannot be bound parameters; the name is validated by the caller and the password is
    # passed through format('%L') so it is quoted server-side.
    template = (
        "ALTER ROLE %I WITH LOGIN PASSWORD %L"
        if exists
        else "CREATE ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD %L"
    )
    stmt: str = conn.execute(
        text(f"SELECT format('{template}', CAST(:r AS text), CAST(:p AS text))"), {"r": role, "p": password}
    ).scalar_one()
    conn.exec_driver_sql(stmt)
    _verify(conn, role)
    conn.exec_driver_sql(GRANT_APP_ROLE_SQL.format(role=role))
    return bool(exists)


def main() -> int:
    role = os.environ.get("VSH_APP_DB_ROLE", "vanshavali_app")
    password = os.environ.get("VSH_APP_DB_PASSWORD", "")
    if not _ROLE_RE.match(role):
        print(f"invalid role name: {role!r}", file=sys.stderr)
        return 2
    if not password:
        print("VSH_APP_DB_PASSWORD is required", file=sys.stderr)
        return 2
    try:
        with get_engine().begin() as conn:
            existed = ensure(conn, role, password)
    except UnsafeRole as exc:
        print(f"refusing: {exc}", file=sys.stderr)
        return 1
    print(
        f"application role {role} {'updated' if existed else 'created'}; attributes verified; grants applied"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
