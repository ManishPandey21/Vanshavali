"""access_grant belongs to the membership

Revision ID: 9c4f2a7d1e83
Revises: 7b3e9d2c4f61
Create Date: 2026-11-09

ADR-0027 §3 / §12.2. ``access_grant`` gains ``membership_id``, a composite FK
``(tree_id, membership_id) -> tree_membership(tree_id, id)`` with ``ON DELETE CASCADE``: removing a
member deletes their grants, a re-invited person starts with none, and a grant can never name a
member of another tree. Backfilled from ``(tree_id, user_id)``; rows with no current membership are
deleted (7b3e9d2c4f61 already removed them; this repeats it in case any appeared since). The unique
constraint moves from ``user_id`` to ``membership_id``. ``user_id`` stays for one release.

Downgrade drops the column and restores the ``user_id`` unique constraint. Deleted orphans are not
restored: they were already unreachable.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "9c4f2a7d1e83"
down_revision: str | None = "7b3e9d2c4f61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("access_grant", sa.Column("membership_id", sa.UUID(), nullable=True))
    op.execute(
        """
        UPDATE access_grant g SET membership_id = m.id
        FROM tree_membership m
        WHERE m.tree_id = g.tree_id AND m.user_id = g.user_id
        """
    )
    op.execute("DELETE FROM access_grant WHERE membership_id IS NULL")
    op.alter_column("access_grant", "membership_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_access_grant_tree_id_membership_id_tree_membership"),
        "access_grant",
        "tree_membership",
        ["tree_id", "membership_id"],
        ["tree_id", "id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("uq_access_grant", "access_grant", type_="unique")
    op.create_unique_constraint(
        "uq_access_grant",
        "access_grant",
        ["tree_id", "membership_id", "resource_type", "resource_id", "permission"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_access_grant", "access_grant", type_="unique")
    op.create_unique_constraint(
        "uq_access_grant",
        "access_grant",
        ["tree_id", "user_id", "resource_type", "resource_id", "permission"],
    )
    op.drop_constraint(
        op.f("fk_access_grant_tree_id_membership_id_tree_membership"), "access_grant", type_="foreignkey"
    )
    op.drop_column("access_grant", "membership_id")
