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

from sqlalchemy import text

from app.core.db import get_engine
from app.models.rls import GRANT_APP_ROLE_SQL

_ROLE_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")


def main() -> int:
    role = os.environ.get("VSH_APP_DB_ROLE", "vanshavali_app")
    password = os.environ.get("VSH_APP_DB_PASSWORD", "")
    if not _ROLE_RE.match(role):
        print(f"invalid role name: {role!r}", file=sys.stderr)
        return 2
    if not password:
        print("VSH_APP_DB_PASSWORD is required", file=sys.stderr)
        return 2
    with get_engine().begin() as conn:
        exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": role}).scalar()
        # Role names cannot be bound parameters; the name is validated above and the password is
        # passed through format('%L') so it is quoted server-side.
        verb = "ALTER" if exists else "CREATE"
        stmt: str = conn.execute(
            text(
                f"SELECT format('{verb} ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE "
                "PASSWORD %L', CAST(:r AS text), CAST(:p AS text))"
            ),
            {"r": role, "p": password},
        ).scalar_one()
        conn.exec_driver_sql(stmt)
        conn.exec_driver_sql(GRANT_APP_ROLE_SQL.format(role=role))
    print(f"application role {role} {'updated' if exists else 'created'}; grants applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
