"""family traditions on the record sharing model (ADR-0027, increment 2)

Revision ID: 8d2e6b4f1a37
Revises: 3f6a8c1d2e94
Create Date: 2026-11-09

* ``tradition_entry.owner_membership_id`` (the author's membership; SET NULL when they leave),
  backfilled from ``created_by`` where that user is still a member.
* ``tradition_entry.privacy_level`` accepts the record audiences ``ONLY_ME`` and ``SELECTED_MEMBERS``.
  Traditions used ``PRIVATE_SELF`` to mean *the author only* (``traditions.may_read``), which is
  exactly ``ONLY_ME``; existing rows are moved to it, so nobody gains or loses access.
* ``access_grant.resource_type`` accepts ``tradition`` ("Selected members" on an entry).

Downgrade deletes tradition grants (no older equivalent), maps ``ONLY_ME`` back to ``PRIVATE_SELF``
(identical meaning under the old ``may_read``) and ``SELECTED_MEMBERS`` to ``CUSTOM`` (admins only:
the selected members lose access), then drops the column.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8d2e6b4f1a37"
down_revision: str | None = "3f6a8c1d2e94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_LEVELS = (
    "PRIVATE_SELF",
    "PRIVATE_TREE_ADMINS",
    "FAMILY_BRANCH",
    "TREE_MEMBERS",
    "INVITED_RESEARCHER",
    "PUBLIC_DECEASED_ONLY",
    "CUSTOM",
)
NEW_LEVELS = ("ONLY_ME", "SELECTED_MEMBERS", *OLD_LEVELS)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    op.add_column(
        "tradition_entry", sa.Column("owner_membership_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.execute(
        """
        UPDATE tradition_entry e SET owner_membership_id = m.id
        FROM tree_membership m
        WHERE m.tree_id = e.tree_id AND m.user_id = e.created_by
        """
    )
    op.create_foreign_key(
        op.f("fk_tradition_entry_tree_id_owner_membership_id_tree_membership"),
        "tradition_entry",
        "tree_membership",
        ["tree_id", "owner_membership_id"],
        ["tree_id", "id"],
        ondelete="SET NULL (owner_membership_id)",
    )
    op.create_index(op.f("ix_tradition_entry_owner_membership_id"), "tradition_entry", ["owner_membership_id"])

    op.drop_constraint(op.f("ck_tradition_entry_tradition_privacy_level"), "tradition_entry", type_="check")
    op.create_check_constraint(
        op.f("ck_tradition_entry_tradition_privacy_level"), "tradition_entry", _in("privacy_level", NEW_LEVELS)
    )
    op.execute("UPDATE tradition_entry SET privacy_level = 'ONLY_ME' WHERE privacy_level = 'PRIVATE_SELF'")

    op.drop_constraint(op.f("ck_access_grant_grantresource"), "access_grant", type_="check")
    op.create_check_constraint(
        op.f("ck_access_grant_grantresource"),
        "access_grant",
        _in("resource_type", ("person", "document", "property", "tradition")),
    )


def downgrade() -> None:
    op.execute("DELETE FROM access_grant WHERE resource_type = 'tradition'")
    op.drop_constraint(op.f("ck_access_grant_grantresource"), "access_grant", type_="check")
    op.create_check_constraint(
        op.f("ck_access_grant_grantresource"),
        "access_grant",
        _in("resource_type", ("person", "document", "property")),
    )

    op.execute("UPDATE tradition_entry SET privacy_level = 'PRIVATE_SELF' WHERE privacy_level = 'ONLY_ME'")
    op.execute("UPDATE tradition_entry SET privacy_level = 'CUSTOM' WHERE privacy_level = 'SELECTED_MEMBERS'")
    op.drop_constraint(op.f("ck_tradition_entry_tradition_privacy_level"), "tradition_entry", type_="check")
    op.create_check_constraint(
        op.f("ck_tradition_entry_tradition_privacy_level"), "tradition_entry", _in("privacy_level", OLD_LEVELS)
    )

    op.drop_index(op.f("ix_tradition_entry_owner_membership_id"), table_name="tradition_entry")
    op.drop_constraint(
        op.f("fk_tradition_entry_tree_id_owner_membership_id_tree_membership"), "tradition_entry", type_="foreignkey"
    )
    op.drop_column("tradition_entry", "owner_membership_id")
