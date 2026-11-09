"""standalone photo collections (ADR-0027 §6, increment 4)

Revision ID: b5c1e7a93d42
Revises: 8d2e6b4f1a37
Create Date: 2026-11-09

* ``photo_collection``: a shareable record of its own (title, description, record audience, owner
  membership, branch audience). New collections are Only me.
* ``photo_collection_item``: a photo (document) in a collection, with its caption, order and cover.
  An item never changes the photo's own audience.
* Both are tree-scoped with row-level security; ``access_grant`` accepts ``collection``.

Downgrade deletes collection grants and drops both tables (the photos stay in the vault).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.models.rls import GRANT_APP_ROLE_SQL, disable_sql, enable_sql

revision: str = "b5c1e7a93d42"
down_revision: str | None = "8d2e6b4f1a37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"
NEW_RLS_TABLES = ("photo_collection", "photo_collection_item")
LEVELS = (
    "ONLY_ME",
    "SELECTED_MEMBERS",
    "PRIVATE_SELF",
    "PRIVATE_TREE_ADMINS",
    "FAMILY_BRANCH",
    "TREE_MEMBERS",
    "INVITED_RESEARCHER",
    "PUBLIC_DECEASED_ONLY",
    "CUSTOM",
)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "photo_collection",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tree_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("privacy_level", sa.String(length=40), server_default="ONLY_ME", nullable=False),
        sa.Column("owner_membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("audience_branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        *_audit_columns(),
        sa.CheckConstraint(
            _in("privacy_level", LEVELS), name=op.f("ck_photo_collection_collection_privacy_level")
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_photo_collection_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "owner_membership_id"],
            ["tree_membership.tree_id", "tree_membership.id"],
            name=op.f("fk_photo_collection_tree_id_owner_membership_id_tree_membership"),
            ondelete="SET NULL (owner_membership_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "audience_branch_id"],
            ["family_branch.tree_id", "family_branch.id"],
            name=op.f("fk_photo_collection_tree_id_audience_branch_id_family_branch"),
            ondelete="SET NULL (audience_branch_id)",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_photo_collection_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_photo_collection_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_photo_collection")),
        sa.UniqueConstraint("tree_id", "id", name="uq_photo_collection_tree_id_id"),
    )
    op.create_index(op.f("ix_photo_collection_tree_id"), "photo_collection", ["tree_id"])
    op.create_index(
        op.f("ix_photo_collection_owner_membership_id"), "photo_collection", ["owner_membership_id"]
    )

    op.create_table(
        "photo_collection_item",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tree_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("collection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("caption", sa.String(length=500), nullable=True),
        sa.Column("is_cover", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_photo_collection_item_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "collection_id"],
            ["photo_collection.tree_id", "photo_collection.id"],
            name=op.f("fk_photo_collection_item_tree_id_collection_id_photo_collection"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "document_id"],
            ["document.tree_id", "document.id"],
            name=op.f("fk_photo_collection_item_tree_id_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_photo_collection_item_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_photo_collection_item_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_photo_collection_item")),
        sa.UniqueConstraint("collection_id", "document_id", name="uq_photo_collection_item"),
        sa.UniqueConstraint("tree_id", "id", name="uq_photo_collection_item_tree_id_id"),
    )
    op.create_index(op.f("ix_photo_collection_item_tree_id"), "photo_collection_item", ["tree_id"])
    op.create_index(op.f("ix_photo_collection_item_document_id"), "photo_collection_item", ["document_id"])
    op.create_index(
        "ix_photo_collection_item_collection",
        "photo_collection_item",
        ["tree_id", "collection_id", "sort_order"],
    )

    op.drop_constraint(op.f("ck_access_grant_grantresource"), "access_grant", type_="check")
    op.create_check_constraint(
        op.f("ck_access_grant_grantresource"),
        "access_grant",
        _in("resource_type", ("person", "document", "property", "tradition", "collection")),
    )

    for table in NEW_RLS_TABLES:
        for stmt in enable_sql(table):
            op.execute(stmt)
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    for table in NEW_RLS_TABLES:
        for stmt in disable_sql(table):
            op.execute(stmt)
    op.execute("DELETE FROM access_grant WHERE resource_type = 'collection'")
    op.drop_constraint(op.f("ck_access_grant_grantresource"), "access_grant", type_="check")
    op.create_check_constraint(
        op.f("ck_access_grant_grantresource"),
        "access_grant",
        _in("resource_type", ("person", "document", "property", "tradition")),
    )
    op.drop_table("photo_collection_item")
    op.drop_table("photo_collection")
