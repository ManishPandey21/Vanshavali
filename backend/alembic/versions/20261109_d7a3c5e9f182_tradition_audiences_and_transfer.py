"""private traditions and ownership transfer

Revision ID: d7a3c5e9f182
Revises: 3f6a8c1d2e94
Create Date: 2026-11-09

ADR-0027 §1, §2 and §12.4, for what 3f6a8c1d2e94 (documents) left out:

- ``tradition_entry.privacy_level`` also takes ``ONLY_ME`` and ``SELECTED_MEMBERS`` (only that
  column's CHECK widens; people and other data keep ``PrivacyLevel``).
- ``GrantResource`` gains ``tradition``, so an entry can be shared with selected members.
- ``tradition_entry.owner_membership_id`` (composite FK, ``SET NULL``), backfilled from
  ``created_by`` where that user is still a member.
- ``pending_owner_membership_id`` on ``document`` and ``tradition_entry``: an ownership transfer
  the owner offered and the recipient has not accepted yet (§2).

Nothing is converted: legacy ``PRIVATE_SELF`` and ``CUSTOM`` entries keep their meaning.

Downgrade maps a tradition's ``ONLY_ME`` to ``PRIVATE_SELF`` (on a tradition that is already
author-only) and ``SELECTED_MEMBERS`` to ``CUSTOM``, deletes tradition grants and drops the columns.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d7a3c5e9f182"
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
OLD_RESOURCES = ("person", "document", "property")
NEW_RESOURCES = (*OLD_RESOURCES, "tradition")

LEVEL_CHECK = "ck_tradition_entry_tradition_privacy_level"
RESOURCE_CHECK = "ck_access_grant_grantresource"


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _checks(levels: Sequence[str], resources: Sequence[str]) -> None:
    op.drop_constraint(op.f(LEVEL_CHECK), "tradition_entry", type_="check")
    op.create_check_constraint(op.f(LEVEL_CHECK), "tradition_entry", _in("privacy_level", levels))
    op.drop_constraint(op.f(RESOURCE_CHECK), "access_grant", type_="check")
    op.create_check_constraint(op.f(RESOURCE_CHECK), "access_grant", _in("resource_type", resources))


def _membership_fk(table: str, column: str) -> None:
    op.create_foreign_key(
        op.f(f"fk_{table}_tree_id_{column}_tree_membership"),
        table,
        "tree_membership",
        ["tree_id", column],
        ["tree_id", "id"],
        ondelete=f"SET NULL ({column})",
    )


def upgrade() -> None:
    _checks(NEW_LEVELS, NEW_RESOURCES)
    op.add_column("tradition_entry", sa.Column("owner_membership_id", sa.UUID(), nullable=True))
    _membership_fk("tradition_entry", "owner_membership_id")
    op.create_index(
        op.f("ix_tradition_entry_owner_membership_id"), "tradition_entry", ["owner_membership_id"]
    )
    op.execute(
        """
        UPDATE tradition_entry e SET owner_membership_id = m.id
        FROM tree_membership m
        WHERE m.tree_id = e.tree_id AND m.user_id = e.created_by
        """
    )
    for table in ("document", "tradition_entry"):
        op.add_column(table, sa.Column("pending_owner_membership_id", sa.UUID(), nullable=True))
        _membership_fk(table, "pending_owner_membership_id")


def downgrade() -> None:
    for table in ("document", "tradition_entry"):
        op.drop_constraint(
            op.f(f"fk_{table}_tree_id_pending_owner_membership_id_tree_membership"), table, type_="foreignkey"
        )
        op.drop_column(table, "pending_owner_membership_id")
    op.drop_index(op.f("ix_tradition_entry_owner_membership_id"), table_name="tradition_entry")
    op.drop_constraint(
        op.f("fk_tradition_entry_tree_id_owner_membership_id_tree_membership"), "tradition_entry", type_="foreignkey"
    )
    op.drop_column("tradition_entry", "owner_membership_id")
    op.execute("UPDATE tradition_entry SET privacy_level = 'PRIVATE_SELF' WHERE privacy_level = 'ONLY_ME'")
    op.execute("UPDATE tradition_entry SET privacy_level = 'CUSTOM' WHERE privacy_level = 'SELECTED_MEMBERS'")
    op.execute("DELETE FROM access_grant WHERE resource_type = 'tradition'")
    _checks(OLD_LEVELS, OLD_RESOURCES)
