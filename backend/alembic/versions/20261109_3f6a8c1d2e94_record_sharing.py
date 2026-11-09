"""record visibility and selective sharing (ADR-0027)

Revision ID: 3f6a8c1d2e94
Revises: 9c4f2a7d1e83
Create Date: 2026-11-09

Grants already belong to memberships (9c4f2a7d1e83, ADR-0027 §3); this adds the record side:

* ``document.owner_membership_id`` (the content owner; SET NULL when they leave), backfilled from
  ``created_by`` where that user is still a member; ``document.audience_branch_id`` ("Selected
  branch"); ``document.allow_download`` (true for existing rows: unchanged behaviour).
* ``document.privacy_level`` also accepts ``ONLY_ME`` and ``SELECTED_MEMBERS``. Other tables keep the
  old CHECK constraint, so people, events and properties can never hold them.

Downgrade maps ``ONLY_ME`` → ``PRIVATE_SELF`` and ``SELECTED_MEMBERS`` → ``CUSTOM`` (the nearest
older levels; both then also admit the tree owner or admins), then drops the columns.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3f6a8c1d2e94"
down_revision: str | None = "9c4f2a7d1e83"
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


def _in(values: tuple[str, ...]) -> str:
    return "privacy_level IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    # ---- document owner, branch audience, download switch
    op.add_column("document", sa.Column("owner_membership_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("document", sa.Column("audience_branch_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column(
        "document", sa.Column("allow_download", sa.Boolean(), server_default="true", nullable=False)
    )
    op.execute(
        """
        UPDATE document d SET owner_membership_id = m.id
        FROM tree_membership m
        WHERE m.tree_id = d.tree_id AND m.user_id = d.created_by
        """
    )
    op.create_foreign_key(
        op.f("fk_document_tree_id_owner_membership_id_tree_membership"),
        "document",
        "tree_membership",
        ["tree_id", "owner_membership_id"],
        ["tree_id", "id"],
        ondelete="SET NULL (owner_membership_id)",
    )
    op.create_foreign_key(
        op.f("fk_document_tree_id_audience_branch_id_family_branch"),
        "document",
        "family_branch",
        ["tree_id", "audience_branch_id"],
        ["tree_id", "id"],
        ondelete="SET NULL (audience_branch_id)",
    )
    op.create_index(op.f("ix_document_owner_membership_id"), "document", ["owner_membership_id"])

    # ---- record-only audiences
    op.drop_constraint(op.f("ck_document_privacylevel"), "document", type_="check")
    op.create_check_constraint(op.f("ck_document_privacylevel"), "document", _in(NEW_LEVELS))


def downgrade() -> None:
    op.execute("UPDATE document SET privacy_level = 'PRIVATE_SELF' WHERE privacy_level = 'ONLY_ME'")
    op.execute("UPDATE document SET privacy_level = 'CUSTOM' WHERE privacy_level = 'SELECTED_MEMBERS'")
    op.drop_constraint(op.f("ck_document_privacylevel"), "document", type_="check")
    op.create_check_constraint(op.f("ck_document_privacylevel"), "document", _in(OLD_LEVELS))

    op.drop_index(op.f("ix_document_owner_membership_id"), table_name="document")
    op.drop_constraint(
        op.f("fk_document_tree_id_audience_branch_id_family_branch"), "document", type_="foreignkey"
    )
    op.drop_constraint(
        op.f("fk_document_tree_id_owner_membership_id_tree_membership"), "document", type_="foreignkey"
    )
    op.drop_column("document", "allow_download")
    op.drop_column("document", "audience_branch_id")
    op.drop_column("document", "owner_membership_id")

