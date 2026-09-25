"""row-level security on tree-scoped tables (second isolation barrier)

Revision ID: b7c1e0d2f3a4
Revises: 880d1a5976ec
Create Date: 2026-09-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.models.rls import GRANT_APP_ROLE_SQL, RLS_TABLES, disable_sql, enable_sql

revision: str = "b7c1e0d2f3a4"
down_revision: str | None = "880d1a5976ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"


def upgrade() -> None:
    for table in RLS_TABLES:
        for stmt in enable_sql(table):
            op.execute(stmt)
    # The application role (non-owner, subject to RLS) gets DML rights if it exists.
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    for table in RLS_TABLES:
        for stmt in disable_sql(table):
            op.execute(stmt)
