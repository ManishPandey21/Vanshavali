"""onboarding attestation and claim invites

Revision ID: a2e3647779fc
Revises: 880d1a5976ec
Create Date: 2026-09-25

ADR-0011: family-data attestations, shareable claim invites, and the claimant's consent on claims.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a2e3647779fc"
down_revision: str | None = "880d1a5976ec"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "family_data_attestation",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("statement_version", sa.String(length=40), nullable=False),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("statement_sha256", sa.String(length=64), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=400), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_family_data_attestation_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_family_data_attestation_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_family_data_attestation_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_family_data_attestation_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_family_data_attestation")),
        sa.UniqueConstraint("tree_id", "id", name="uq_family_data_attestation_tree_id_id"),
    )
    op.create_index(
        op.f("ix_family_data_attestation_tree_id"), "family_data_attestation", ["tree_id"], unique=False
    )
    op.create_index(
        "ix_family_data_attestation_user", "family_data_attestation", ["tree_id", "user_id"], unique=False
    )
    op.create_table(
        "profile_claim_invite",
        sa.Column("person_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "offered_role",
            sa.Enum(
                "OWNER",
                "FAMILY_ADMIN",
                "BRANCH_ADMIN",
                "CONTRIBUTOR",
                "RESEARCHER",
                "VIEWER",
                "DOCUMENT_CUSTODIAN",
                "PROPERTY_CUSTODIAN",
                name="claim_invite_role",
                native_enum=False,
                create_constraint=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("branch_id", sa.UUID(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_by", sa.UUID(), nullable=True),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tree_id", sa.UUID(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "offered_role IN ('OWNER', 'FAMILY_ADMIN', 'BRANCH_ADMIN', 'CONTRIBUTOR', 'RESEARCHER', 'VIEWER', 'DOCUMENT_CUSTODIAN', 'PROPERTY_CUSTODIAN')",
            name=op.f("ck_profile_claim_invite_claim_invite_role"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["app_user.id"],
            name=op.f("fk_profile_claim_invite_created_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "branch_id"],
            ["family_branch.tree_id", "family_branch.id"],
            name=op.f("fk_profile_claim_invite_tree_id_branch_id_family_branch"),
            ondelete="SET NULL (branch_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "person_id"],
            ["person.tree_id", "person.id"],
            name=op.f("fk_profile_claim_invite_tree_id_person_id_person"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id"], ["tree.id"], name=op.f("fk_profile_claim_invite_tree_id_tree"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by"],
            ["app_user.id"],
            name=op.f("fk_profile_claim_invite_updated_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["used_by"],
            ["app_user.id"],
            name=op.f("fk_profile_claim_invite_used_by_app_user"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_profile_claim_invite")),
        sa.UniqueConstraint("token_hash", name="uq_profile_claim_invite_token_hash"),
        sa.UniqueConstraint("tree_id", "id", name="uq_profile_claim_invite_tree_id_id"),
    )
    op.create_index(
        "ix_profile_claim_invite_person", "profile_claim_invite", ["tree_id", "person_id"], unique=False
    )
    op.create_index(
        op.f("ix_profile_claim_invite_tree_id"), "profile_claim_invite", ["tree_id"], unique=False
    )
    op.add_column("profile_claim", sa.Column("invite_id", sa.UUID(), nullable=True))
    op.add_column("profile_claim", sa.Column("consent_version", sa.String(length=40), nullable=True))
    op.add_column("profile_claim", sa.Column("consent_language", sa.String(length=10), nullable=True))
    op.add_column("profile_claim", sa.Column("consent_sha256", sa.String(length=64), nullable=True))
    op.add_column("profile_claim", sa.Column("consent_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        op.f("fk_profile_claim_tree_id_invite_id_profile_claim_invite"),
        "profile_claim",
        "profile_claim_invite",
        ["tree_id", "invite_id"],
        ["tree_id", "id"],
        ondelete="SET NULL (invite_id)",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_profile_claim_tree_id_invite_id_profile_claim_invite"), "profile_claim", type_="foreignkey"
    )
    op.drop_column("profile_claim", "consent_at")
    op.drop_column("profile_claim", "consent_sha256")
    op.drop_column("profile_claim", "consent_language")
    op.drop_column("profile_claim", "consent_version")
    op.drop_column("profile_claim", "invite_id")
    op.drop_index(op.f("ix_profile_claim_invite_tree_id"), table_name="profile_claim_invite")
    op.drop_index("ix_profile_claim_invite_person", table_name="profile_claim_invite")
    op.drop_table("profile_claim_invite")
    op.drop_index("ix_family_data_attestation_user", table_name="family_data_attestation")
    op.drop_index(op.f("ix_family_data_attestation_tree_id"), table_name="family_data_attestation")
    op.drop_table("family_data_attestation")
