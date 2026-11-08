"""change proposals and family review

Revision ID: 4d7c2a9e1b58
Revises: 8e4a1f6c2b37
Create Date: 2026-11-07

ADR-0021: `revision` and `review_state` on person, name_record, event, relationship and
assertion; `tree.review_policy`; `change_proposal`, `change_proposal_item`, `proposal_citation`,
`proposal_comment`, `record_revision` and `user_notification`, all tree-scoped with row-level
security; the REVIEWER role is allowed in claim-invite offers.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.models.rls import GRANT_APP_ROLE_SQL, disable_sql, enable_sql

revision: str = "4d7c2a9e1b58"
down_revision: str | None = "8e4a1f6c2b37"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"
# Frozen at this revision (see b7c1e0d2f3a4).
NEW_RLS_TABLES: tuple[str, ...] = (
    "change_proposal",
    "change_proposal_item",
    "proposal_citation",
    "proposal_comment",
    "record_revision",
    "user_notification",
)
REVIEWED_TABLES: tuple[str, ...] = ("assertion", "event", "name_record", "person", "relationship")
ROLES_BEFORE = "'OWNER', 'FAMILY_ADMIN', 'BRANCH_ADMIN', 'CONTRIBUTOR', 'RESEARCHER', 'VIEWER', 'DOCUMENT_CUSTODIAN', 'PROPERTY_CUSTODIAN'"


def upgrade() -> None:
    op.create_table(
        "change_proposal",
        sa.Column("proposer_id", sa.UUID(), nullable=True),
        sa.Column(
            "kind",
            sa.Enum(
                "change",
                "challenge",
                name="proposalkind",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "awaiting_review",
                "accepted",
                "rejected",
                "withdrawn",
                "stale",
                name="change_proposal_status",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("rationale", sa.Text(), server_default="", nullable=False),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column(
            "target_type",
            sa.Enum(
                "person",
                "name",
                "event",
                "relationship",
                "assertion",
                name="challenge_target_type",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=True,
        ),
        sa.Column("target_id", sa.UUID(), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("stale_reason", sa.Text(), nullable=True),
        sa.Column("supersedes_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("kind IN ('change', 'challenge')", name=op.f("ck_change_proposal_proposalkind")),
        sa.CheckConstraint(
            "status IN ('draft', 'awaiting_review', 'accepted', 'rejected', 'withdrawn', 'stale')",
            name=op.f("ck_change_proposal_change_proposal_status"),
        ),
        sa.CheckConstraint(
            "target_type IN ('person', 'name', 'event', 'relationship', 'assertion')",
            name=op.f("ck_change_proposal_challenge_target_type"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_change_proposal_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "supersedes_id"],
            ["change_proposal.tree_id", "change_proposal.id"],
            name=op.f("fk_change_proposal_tree_id_supersedes_id_change_proposal"),
            ondelete="SET NULL (supersedes_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_change_proposal_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_change_proposal_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_proposal")),
        sa.UniqueConstraint("tree_id", "id", name="uq_change_proposal_tree_id_id"),
    )
    op.create_index("ix_change_proposal_person", "change_proposal", ["tree_id", "person_id"], unique=False)
    op.create_index(
        "ix_change_proposal_status", "change_proposal", ["tree_id", "status", "created_at"], unique=False
    )
    op.create_index(op.f("ix_change_proposal_tree_id"), "change_proposal", ["tree_id"], unique=False)
    op.create_table(
        "record_revision",
        sa.Column(
            "record_type",
            sa.Enum(
                "person",
                "name",
                "event",
                "relationship",
                "assertion",
                name="reviewtarget",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("record_id", sa.UUID(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "op",
            sa.Enum(
                "create",
                "update",
                "delete",
                name="proposalop",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column("person_b_id", sa.UUID(), nullable=True),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("proposal_id", sa.UUID(), nullable=True),
        sa.Column("reviewer_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "op IN ('create', 'update', 'delete')", name=op.f("ck_record_revision_proposalop")
        ),
        sa.CheckConstraint(
            "record_type IN ('person', 'name', 'event', 'relationship', 'assertion')",
            name=op.f("ck_record_revision_reviewtarget"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_record_revision_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_record_revision_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_record_revision_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_record_revision")),
        sa.UniqueConstraint("tree_id", "id", name="uq_record_revision_tree_id_id"),
    )
    op.create_index(
        "ix_record_revision_person", "record_revision", ["tree_id", "person_id", "created_at"], unique=False
    )
    op.create_index(
        "ix_record_revision_person_b", "record_revision", ["tree_id", "person_b_id"], unique=False
    )
    op.create_index(
        "ix_record_revision_record",
        "record_revision",
        ["tree_id", "record_type", "record_id", "revision"],
        unique=False,
    )
    op.create_index(op.f("ix_record_revision_tree_id"), "record_revision", ["tree_id"], unique=False)
    op.create_table(
        "user_notification",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "proposal_to_review",
                "proposal_accepted",
                "proposal_rejected",
                "proposal_stale",
                "challenge_opened",
                "challenge_upheld",
                "challenge_dismissed",
                "proposal_comment",
                name="notificationkind",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("proposal_id", sa.UUID(), nullable=True),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "kind IN ('proposal_to_review', 'proposal_accepted', 'proposal_rejected', 'proposal_stale', 'challenge_opened', 'challenge_upheld', 'challenge_dismissed', 'proposal_comment')",
            name=op.f("ck_user_notification_notificationkind"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_user_notification_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_user_notification_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_user_notification_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_notification")),
        sa.UniqueConstraint("tree_id", "id", name="uq_user_notification_tree_id_id"),
    )
    op.create_index(op.f("ix_user_notification_tree_id"), "user_notification", ["tree_id"], unique=False)
    op.create_index(
        "ix_user_notification_user",
        "user_notification",
        ["tree_id", "user_id", "read_at", "created_at"],
        unique=False,
    )
    op.create_table(
        "change_proposal_item",
        sa.Column("proposal_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "target_type",
            sa.Enum(
                "person",
                "name",
                "event",
                "relationship",
                "assertion",
                name="reviewtarget",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "op",
            sa.Enum(
                "create",
                "update",
                "delete",
                name="proposalop",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("target_id", sa.UUID(), nullable=True),
        sa.Column("person_id", sa.UUID(), nullable=True),
        sa.Column("patch", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column(
            "base_revisions", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "op IN ('create', 'update', 'delete')", name=op.f("ck_change_proposal_item_proposalop")
        ),
        sa.CheckConstraint(
            "target_type IN ('person', 'name', 'event', 'relationship', 'assertion')",
            name=op.f("ck_change_proposal_item_reviewtarget"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_change_proposal_item_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "proposal_id"],
            ["change_proposal.tree_id", "change_proposal.id"],
            name=op.f("fk_change_proposal_item_tree_id_proposal_id_change_proposal"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_change_proposal_item_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_change_proposal_item_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_proposal_item")),
        sa.UniqueConstraint("tree_id", "id", name="uq_change_proposal_item_tree_id_id"),
    )
    op.create_index(
        "ix_change_proposal_item_proposal", "change_proposal_item", ["tree_id", "proposal_id"], unique=False
    )
    op.create_index(
        "ix_change_proposal_item_target",
        "change_proposal_item",
        ["tree_id", "target_type", "target_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_change_proposal_item_tree_id"), "change_proposal_item", ["tree_id"], unique=False
    )
    op.create_table(
        "proposal_comment",
        sa.Column("proposal_id", sa.UUID(), nullable=False),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_proposal_comment_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "proposal_id"],
            ["change_proposal.tree_id", "change_proposal.id"],
            name=op.f("fk_proposal_comment_tree_id_proposal_id_change_proposal"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_proposal_comment_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_proposal_comment_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proposal_comment")),
        sa.UniqueConstraint("tree_id", "id", name="uq_proposal_comment_tree_id_id"),
    )
    op.create_index(
        "ix_proposal_comment_proposal",
        "proposal_comment",
        ["tree_id", "proposal_id", "created_at"],
        unique=False,
    )
    op.create_index(op.f("ix_proposal_comment_tree_id"), "proposal_comment", ["tree_id"], unique=False)
    op.create_table(
        "proposal_citation",
        sa.Column("proposal_id", sa.UUID(), nullable=False),
        sa.Column("source_id", sa.UUID(), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_proposal_citation_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "proposal_id"],
            ["change_proposal.tree_id", "change_proposal.id"],
            name=op.f("fk_proposal_citation_tree_id_proposal_id_change_proposal"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "source_id"],
            ["source.tree_id", "source.id"],
            name=op.f("fk_proposal_citation_tree_id_source_id_source"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_proposal_citation_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_proposal_citation_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_proposal_citation")),
        sa.UniqueConstraint("tree_id", "id", name="uq_proposal_citation_tree_id_id"),
    )
    op.create_index(
        "ix_proposal_citation_proposal", "proposal_citation", ["tree_id", "proposal_id"], unique=False
    )
    op.create_index(op.f("ix_proposal_citation_tree_id"), "proposal_citation", ["tree_id"], unique=False)
    op.add_column("assertion", sa.Column("revision", sa.Integer(), server_default="1", nullable=False))
    op.add_column(
        "assertion",
        sa.Column(
            "review_state",
            sa.Enum(
                "unreviewed",
                "family_reviewed",
                "contested",
                name="reviewstate",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="unreviewed",
            nullable=False,
        ),
    )
    op.add_column("assertion", sa.Column("review_state_by", sa.UUID(), nullable=True))
    op.add_column("assertion", sa.Column("review_state_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("event", sa.Column("revision", sa.Integer(), server_default="1", nullable=False))
    op.add_column(
        "event",
        sa.Column(
            "review_state",
            sa.Enum(
                "unreviewed",
                "family_reviewed",
                "contested",
                name="reviewstate",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="unreviewed",
            nullable=False,
        ),
    )
    op.add_column("event", sa.Column("review_state_by", sa.UUID(), nullable=True))
    op.add_column("event", sa.Column("review_state_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("name_record", sa.Column("revision", sa.Integer(), server_default="1", nullable=False))
    op.add_column(
        "name_record",
        sa.Column(
            "review_state",
            sa.Enum(
                "unreviewed",
                "family_reviewed",
                "contested",
                name="reviewstate",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="unreviewed",
            nullable=False,
        ),
    )
    op.add_column("name_record", sa.Column("review_state_by", sa.UUID(), nullable=True))
    op.add_column("name_record", sa.Column("review_state_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("person", sa.Column("revision", sa.Integer(), server_default="1", nullable=False))
    op.add_column(
        "person",
        sa.Column(
            "review_state",
            sa.Enum(
                "unreviewed",
                "family_reviewed",
                "contested",
                name="reviewstate",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="unreviewed",
            nullable=False,
        ),
    )
    op.add_column("person", sa.Column("review_state_by", sa.UUID(), nullable=True))
    op.add_column("person", sa.Column("review_state_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("relationship", sa.Column("revision", sa.Integer(), server_default="1", nullable=False))
    op.add_column(
        "relationship",
        sa.Column(
            "review_state",
            sa.Enum(
                "unreviewed",
                "family_reviewed",
                "contested",
                name="reviewstate",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="unreviewed",
            nullable=False,
        ),
    )
    op.add_column("relationship", sa.Column("review_state_by", sa.UUID(), nullable=True))
    op.add_column("relationship", sa.Column("review_state_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "tree",
        sa.Column(
            "review_policy",
            sa.Enum(
                "off",
                "structure",
                "all",
                name="reviewpolicy",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            server_default="off",
            nullable=False,
        ),
    )

    for table in REVIEWED_TABLES:
        op.create_check_constraint(
            op.f(f"ck_{table}_reviewstate"),
            table,
            "review_state IN ('unreviewed', 'family_reviewed', 'contested')",
        )
    op.create_check_constraint(
        op.f("ck_tree_reviewpolicy"), "tree", "review_policy IN ('off', 'structure', 'all')"
    )
    op.drop_constraint(
        op.f("ck_profile_claim_invite_claim_invite_role"), "profile_claim_invite", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_profile_claim_invite_claim_invite_role"),
        "profile_claim_invite",
        f"offered_role IN ({ROLES_BEFORE}, 'REVIEWER')",
    )
    for table in NEW_RLS_TABLES:
        for stmt in enable_sql(table):
            op.execute(stmt)
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    for table in NEW_RLS_TABLES:
        for stmt in disable_sql(table):
            op.execute(stmt)
    op.drop_constraint(
        op.f("ck_profile_claim_invite_claim_invite_role"), "profile_claim_invite", type_="check"
    )
    op.create_check_constraint(
        op.f("ck_profile_claim_invite_claim_invite_role"),
        "profile_claim_invite",
        f"offered_role IN ({ROLES_BEFORE})",
    )
    op.drop_constraint(op.f("ck_tree_reviewpolicy"), "tree", type_="check")
    for table in REVIEWED_TABLES:
        op.drop_constraint(op.f(f"ck_{table}_reviewstate"), table, type_="check")
    op.drop_column("tree", "review_policy")
    op.drop_column("relationship", "review_state_at")
    op.drop_column("relationship", "review_state_by")
    op.drop_column("relationship", "review_state")
    op.drop_column("relationship", "revision")
    op.drop_column("person", "review_state_at")
    op.drop_column("person", "review_state_by")
    op.drop_column("person", "review_state")
    op.drop_column("person", "revision")
    op.drop_column("name_record", "review_state_at")
    op.drop_column("name_record", "review_state_by")
    op.drop_column("name_record", "review_state")
    op.drop_column("name_record", "revision")
    op.drop_column("event", "review_state_at")
    op.drop_column("event", "review_state_by")
    op.drop_column("event", "review_state")
    op.drop_column("event", "revision")
    op.drop_column("assertion", "review_state_at")
    op.drop_column("assertion", "review_state_by")
    op.drop_column("assertion", "review_state")
    op.drop_column("assertion", "revision")
    op.drop_index(op.f("ix_proposal_citation_tree_id"), table_name="proposal_citation")
    op.drop_index("ix_proposal_citation_proposal", table_name="proposal_citation")
    op.drop_table("proposal_citation")
    op.drop_index(op.f("ix_proposal_comment_tree_id"), table_name="proposal_comment")
    op.drop_index("ix_proposal_comment_proposal", table_name="proposal_comment")
    op.drop_table("proposal_comment")
    op.drop_index(op.f("ix_change_proposal_item_tree_id"), table_name="change_proposal_item")
    op.drop_index("ix_change_proposal_item_target", table_name="change_proposal_item")
    op.drop_index("ix_change_proposal_item_proposal", table_name="change_proposal_item")
    op.drop_table("change_proposal_item")
    op.drop_index("ix_user_notification_user", table_name="user_notification")
    op.drop_index(op.f("ix_user_notification_tree_id"), table_name="user_notification")
    op.drop_table("user_notification")
    op.drop_index(op.f("ix_record_revision_tree_id"), table_name="record_revision")
    op.drop_index("ix_record_revision_record", table_name="record_revision")
    op.drop_index("ix_record_revision_person_b", table_name="record_revision")
    op.drop_index("ix_record_revision_person", table_name="record_revision")
    op.drop_table("record_revision")
    op.drop_index(op.f("ix_change_proposal_tree_id"), table_name="change_proposal")
    op.drop_index("ix_change_proposal_status", table_name="change_proposal")
    op.drop_index("ix_change_proposal_person", table_name="change_proposal")
    op.drop_table("change_proposal")
