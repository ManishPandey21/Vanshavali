"""cultural depth: offers, kinship words, traditions

Revision ID: 6a1d9c3e5f27
Revises: 4d7c2a9e1b58
Create Date: 2026-11-08

ADR-0026: offer columns on `tree_vocabulary_term`; `kinship_override`, `tradition_entry` and
`tradition_link`, all tree-scoped with row-level security; the kinship-word preference on
`app_user` and the tree default on `tree`; `tradition` as a citation and document-link target;
`tradition` and `kinship_word` as review targets (revision history, proposals); offer
decisions as notifications (`user_notification.subject_id`).

The new heritage attributes (devak, ancestral_occupation, family_language) need no schema change:
`assertion.attribute` is validated by the API, not by a CHECK constraint.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.models.rls import GRANT_APP_ROLE_SQL, disable_sql, enable_sql

revision: str = "6a1d9c3e5f27"
down_revision: str | None = "4d7c2a9e1b58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"
# Frozen at this revision (see b7c1e0d2f3a4).
NEW_RLS_TABLES: tuple[str, ...] = ("kinship_override", "tradition_entry", "tradition_link")

PRIVACY = "'PRIVATE_SELF', 'PRIVATE_TREE_ADMINS', 'FAMILY_BRANCH', 'TREE_MEMBERS', 'INVITED_RESEARCHER', 'PUBLIC_DECEASED_ONLY', 'CUSTOM'"
REVIEW_STATES = "'unreviewed', 'family_reviewed', 'contested'"
REVIEW_TARGETS_BEFORE = "'person', 'name', 'event', 'relationship', 'assertion'"
REVIEW_TARGETS_AFTER = REVIEW_TARGETS_BEFORE + ", 'tradition', 'kinship_word'"
CITATION_BEFORE = (
    "'person', 'name_record', 'event', 'relationship', 'assertion', 'astrology_profile', "
    "'property', 'land_parcel', 'property_interest', 'property_event', 'household'"
)
DOCLINK_BEFORE = (
    "'person', 'event', 'relationship', 'place', 'property', 'land_parcel', 'property_event', "
    "'source', 'household'"
)
NOTIFICATION_KINDS_BEFORE = (
    "'proposal_to_review', 'proposal_accepted', 'proposal_rejected', 'proposal_stale', "
    "'challenge_opened', 'challenge_upheld', 'challenge_dismissed', 'proposal_comment'"
)
# (table, constraint suffix, column, values before)
CHECKS: tuple[tuple[str, str, str, str], ...] = (
    ("citation", "citationtarget", "target_type", CITATION_BEFORE),
    ("document_link", "documentlinktarget", "target_type", DOCLINK_BEFORE),
    ("record_revision", "reviewtarget", "record_type", REVIEW_TARGETS_BEFORE),
    ("change_proposal_item", "reviewtarget", "target_type", REVIEW_TARGETS_BEFORE),
    ("change_proposal", "challenge_target_type", "target_type", REVIEW_TARGETS_BEFORE),
    ("user_notification", "notificationkind", "kind", NOTIFICATION_KINDS_BEFORE),
)
ADDED = {
    "citationtarget": ", 'tradition'",
    "documentlinktarget": ", 'tradition'",
    "reviewtarget": ", 'tradition', 'kinship_word'",
    "challenge_target_type": ", 'tradition', 'kinship_word'",
    "notificationkind": ", 'offer_accepted', 'offer_declined'",
}


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def _review_columns() -> list[sa.Column]:
    return [
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("review_state", sa.String(length=40), server_default="unreviewed", nullable=False),
        sa.Column("review_state_by", sa.UUID(), nullable=True),
        sa.Column("review_state_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _audit_constraints(table: str) -> list[sa.Constraint]:
    return [
        sa.ForeignKeyConstraint(
            ["created_by"], ["app_user.id"], name=op.f(f"fk_{table}_created_by_app_user"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"], ["app_user.id"], name=op.f(f"fk_{table}_updated_by_app_user"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f(f"fk_{table}_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.UniqueConstraint("tree_id", "id", name=f"uq_{table}_tree_id_id"),
    ]


def upgrade() -> None:
    op.create_table(
        "kinship_override",
        sa.Column("pattern", sa.String(length=200), nullable=False),
        sa.Column("lang", sa.String(length=16), nullable=False),
        sa.Column("region", sa.String(length=40), nullable=True),
        sa.Column("word", sa.String(length=120), nullable=False),
        sa.Column("branch_id", sa.UUID(), nullable=True),
        *_audit_columns(),
        *_review_columns(),
        *_audit_constraints("kinship_override"),
        sa.CheckConstraint(
            f"review_state IN ({REVIEW_STATES})", name=op.f("ck_kinship_override_reviewstate")
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "branch_id"],
            ["family_branch.tree_id", "family_branch.id"],
            name=op.f("fk_kinship_override_tree_id_branch_id_family_branch"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tree_id",
            "pattern",
            "lang",
            "branch_id",
            name="uq_kinship_override_pattern",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index(op.f("ix_kinship_override_tree_id"), "kinship_override", ["tree_id"])

    op.create_table(
        "tradition_entry",
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("body", sa.Text(), server_default="", nullable=False),
        sa.Column("language", sa.String(length=16), nullable=True),
        sa.Column("script", sa.String(length=16), nullable=True),
        sa.Column("branch_id", sa.UUID(), nullable=True),
        sa.Column("privacy_level", sa.String(length=40), server_default="TREE_MEMBERS", nullable=False),
        sa.Column("search_text", sa.Text(), server_default="", nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        *_review_columns(),
        *_audit_constraints("tradition_entry"),
        sa.CheckConstraint(
            "kind IN ('ritual_guide', 'custom', 'song', 'recipe', 'story', 'other')",
            name=op.f("ck_tradition_entry_traditionkind"),
        ),
        sa.CheckConstraint(
            f"privacy_level IN ({PRIVACY})", name=op.f("ck_tradition_entry_tradition_privacy_level")
        ),
        sa.CheckConstraint(f"review_state IN ({REVIEW_STATES})", name=op.f("ck_tradition_entry_reviewstate")),
        sa.ForeignKeyConstraint(
            ["tree_id", "branch_id"],
            ["family_branch.tree_id", "family_branch.id"],
            name=op.f("fk_tradition_entry_tree_id_branch_id_family_branch"),
            ondelete="SET NULL (branch_id)",
        ),
    )
    op.create_index(op.f("ix_tradition_entry_tree_id"), "tradition_entry", ["tree_id"])
    op.create_index("ix_tradition_entry_tree_kind", "tradition_entry", ["tree_id", "kind"])
    op.create_index(
        "ix_tradition_entry_search_trgm",
        "tradition_entry",
        ["search_text"],
        postgresql_using="gin",
        postgresql_ops={"search_text": "gin_trgm_ops"},
    )

    op.create_table(
        "tradition_link",
        sa.Column("tradition_id", sa.UUID(), nullable=False),
        sa.Column("target_type", sa.String(length=40), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        *_audit_columns(),
        *_audit_constraints("tradition_link"),
        sa.CheckConstraint(
            "target_type IN ('person', 'event', 'place')", name=op.f("ck_tradition_link_traditionlinktarget")
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "tradition_id"],
            ["tradition_entry.tree_id", "tradition_entry.id"],
            name=op.f("fk_tradition_link_tree_id_tradition_id_tradition_entry"),
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tradition_id", "target_type", "target_id", name="uq_tradition_link"),
    )
    op.create_index(op.f("ix_tradition_link_tree_id"), "tradition_link", ["tree_id"])
    op.create_index("ix_tradition_link_target", "tradition_link", ["tree_id", "target_type", "target_id"])

    op.add_column("app_user", sa.Column("kinship_lang", sa.String(length=16), nullable=True))
    op.add_column("app_user", sa.Column("kinship_region", sa.String(length=40), nullable=True))
    op.add_column("tree", sa.Column("kinship_lang", sa.String(length=16), nullable=True))
    op.add_column("tree", sa.Column("kinship_region", sa.String(length=40), nullable=True))

    op.add_column(
        "tree_vocabulary_term",
        sa.Column("offer_status", sa.String(length=40), server_default="none", nullable=False),
    )
    op.add_column("tree_vocabulary_term", sa.Column("offered_by", sa.UUID(), nullable=True))
    op.add_column("tree_vocabulary_term", sa.Column("offered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("tree_vocabulary_term", sa.Column("offer_note", sa.String(length=500), nullable=True))
    op.add_column("tree_vocabulary_term", sa.Column("offer_temple", sa.String(length=200), nullable=True))
    op.add_column("tree_vocabulary_term", sa.Column("promoted_code", sa.String(length=80), nullable=True))
    op.create_check_constraint(
        op.f("ck_tree_vocabulary_term_offerstatus"),
        "tree_vocabulary_term",
        "offer_status IN ('none', 'offered', 'accepted', 'declined')",
    )
    op.create_foreign_key(
        op.f("fk_tree_vocabulary_term_offered_by_app_user"),
        "tree_vocabulary_term",
        "app_user",
        ["offered_by"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column("user_notification", sa.Column("subject_id", sa.UUID(), nullable=True))
    for table, suffix, column, before in CHECKS:
        name = op.f(f"ck_{table}_{suffix}")
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"{column} IN ({before}{ADDED[suffix]})")

    for table in NEW_RLS_TABLES:
        for stmt in enable_sql(table):
            op.execute(stmt)
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    for table in NEW_RLS_TABLES:
        for stmt in disable_sql(table):
            op.execute(stmt)

    # rows that only the new values allow cannot survive the old constraints
    op.execute("DELETE FROM citation WHERE target_type = 'tradition'")
    op.execute("DELETE FROM document_link WHERE target_type = 'tradition'")
    op.execute("DELETE FROM user_notification WHERE kind IN ('offer_accepted', 'offer_declined')")
    op.execute("DELETE FROM record_revision WHERE record_type IN ('tradition', 'kinship_word')")
    op.execute(
        "DELETE FROM change_proposal WHERE target_type IN ('tradition', 'kinship_word') OR id IN "
        "(SELECT proposal_id FROM change_proposal_item WHERE target_type IN ('tradition', 'kinship_word'))"
    )
    for table, suffix, column, before in CHECKS:
        name = op.f(f"ck_{table}_{suffix}")
        op.drop_constraint(name, table, type_="check")
        op.create_check_constraint(name, table, f"{column} IN ({before})")
    op.drop_column("user_notification", "subject_id")

    op.drop_constraint(
        op.f("fk_tree_vocabulary_term_offered_by_app_user"), "tree_vocabulary_term", type_="foreignkey"
    )
    op.drop_constraint(op.f("ck_tree_vocabulary_term_offerstatus"), "tree_vocabulary_term", type_="check")
    for column in ("promoted_code", "offer_temple", "offer_note", "offered_at", "offered_by", "offer_status"):
        op.drop_column("tree_vocabulary_term", column)
    for table in ("tree", "app_user"):
        op.drop_column(table, "kinship_region")
        op.drop_column(table, "kinship_lang")

    op.drop_index("ix_tradition_link_target", table_name="tradition_link")
    op.drop_index(op.f("ix_tradition_link_tree_id"), table_name="tradition_link")
    op.drop_table("tradition_link")
    op.drop_index("ix_tradition_entry_search_trgm", table_name="tradition_entry")
    op.drop_index("ix_tradition_entry_tree_kind", table_name="tradition_entry")
    op.drop_index(op.f("ix_tradition_entry_tree_id"), table_name="tradition_entry")
    op.drop_table("tradition_entry")
    op.drop_index(op.f("ix_kinship_override_tree_id"), table_name="kinship_override")
    op.drop_table("kinship_override")
