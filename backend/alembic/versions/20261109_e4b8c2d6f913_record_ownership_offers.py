"""ownership offers on shareable records

Revision ID: e4b8c2d6f913
Revises: b5c1e7a93d42
Create Date: 2026-11-09

ADR-0027 §2: the owner of a document, tradition entry or photo collection may offer it to another
member, who becomes the owner only by accepting. ``pending_owner_membership_id`` holds the offer: a
composite FK to ``tree_membership`` with ``ON DELETE SET NULL`` (an offer to someone who leaves
lapses). Nothing is backfilled: no record has an offer yet.

Downgrade drops the column; pending offers are lost (no access changes: an offer gives none).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e4b8c2d6f913"
down_revision: str | None = "b5c1e7a93d42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("document", "tradition_entry", "photo_collection")
COLUMN = "pending_owner_membership_id"


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column(COLUMN, sa.UUID(), nullable=True))
        op.create_foreign_key(
            op.f(f"fk_{table}_tree_id_{COLUMN}_tree_membership"),
            table,
            "tree_membership",
            ["tree_id", COLUMN],
            ["tree_id", "id"],
            ondelete=f"SET NULL ({COLUMN})",
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_constraint(op.f(f"fk_{table}_tree_id_{COLUMN}_tree_membership"), table, type_="foreignkey")
        op.drop_column(table, COLUMN)
