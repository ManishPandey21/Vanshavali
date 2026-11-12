"""reusable family and ancestral addresses (ADR-0031 section 5)

Revision ID: d4a8e6f1b209
Revises: c8f4a2d7e901
Create Date: 2026-11-12
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.downgrade_guard import LossyDowngrade, refuse_lossy_downgrades
from app.models.rls import disable_sql, enable_sql

revision: str = "d4a8e6f1b209"
down_revision: str | None = "c8f4a2d7e901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RECORD_LEVELS = (
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


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tree_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tree_id"], ["tree.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["updated_by"], ["app_user.id"], ondelete="SET NULL"),
    ]


def _record_privacy() -> sa.Enum:
    return sa.Enum(
        *RECORD_LEVELS,
        name="recordprivacylevel",
        native_enum=False,
        create_constraint=True,
        length=40,
    )


def upgrade() -> None:
    grant_check = op.f("ck_access_grant_grantresource")
    op.drop_constraint(grant_check, "access_grant", type_="check")
    op.create_check_constraint(
        grant_check,
        "access_grant",
        "resource_type IN ('person', 'document', 'property', 'tradition', 'collection', 'family_address')",
    )

    op.create_table(
        "family_address",
        *_audit_columns(),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("controller_membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("privacy_level", _record_privacy(), nullable=False),
        sa.Column("audience_branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("household_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("property_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("place_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("ancestral_assertion_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("current_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("sharing_released", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("retired_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tree_id", "controller_membership_id"],
            ["tree_membership.tree_id", "tree_membership.id"],
            ondelete="SET NULL (controller_membership_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "audience_branch_id"],
            ["family_branch.tree_id", "family_branch.id"],
            ondelete="SET NULL (audience_branch_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "branch_id"],
            ["family_branch.tree_id", "family_branch.id"],
            ondelete="SET NULL (branch_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "household_id"],
            ["household.tree_id", "household.id"],
            ondelete="SET NULL (household_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "property_id"], ["property.tree_id", "property.id"], ondelete="SET NULL (property_id)"
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "place_id"], ["place.tree_id", "place.id"], ondelete="SET NULL (place_id)"
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "ancestral_assertion_id"],
            ["assertion.tree_id", "assertion.id"],
            ondelete="SET NULL (ancestral_assertion_id)",
        ),
        sa.UniqueConstraint("tree_id", "id", name="uq_family_address_tree_id_id"),
        sa.UniqueConstraint(
            "tree_id", "controller_membership_id", "idempotency_key", name="uq_family_address_idempotency"
        ),
    )
    op.create_index("ix_family_address_tree_id", "family_address", ["tree_id"])
    op.create_index("ix_family_address_branch", "family_address", ["tree_id", "branch_id"])
    op.create_index("ix_family_address_place", "family_address", ["tree_id", "place_id"])

    op.create_table(
        "family_address_version",
        *_audit_columns(),
        sa.Column("family_address_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("place_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("locality", sa.String(200), nullable=True),
        sa.Column("sub_district", sa.String(160), nullable=True),
        sa.Column("district", sa.String(120), nullable=True),
        sa.Column("state", sa.String(120), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("payload_enc", sa.Text(), nullable=False),
        sa.Column("source_ancestral_assertion_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("root_source_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason_enc", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tree_id", "family_address_id"],
            ["family_address.tree_id", "family_address.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "place_id"], ["place.tree_id", "place.id"], ondelete="SET NULL (place_id)"
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "source_ancestral_assertion_id"],
            ["assertion.tree_id", "assertion.id"],
            ondelete="SET NULL (source_ancestral_assertion_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "root_source_version_id"],
            ["family_address_version.tree_id", "family_address_version.id"],
            ondelete="SET NULL (root_source_version_id)",
        ),
        sa.UniqueConstraint("tree_id", "id", name="uq_family_address_version_tree_id_id"),
        sa.UniqueConstraint(
            "tree_id", "family_address_id", "version", name="uq_family_address_version_number"
        ),
        sa.CheckConstraint(
            "source_ancestral_assertion_id IS NULL OR root_source_version_id IS NULL",
            name="ck_family_address_version_ancestral_source_is_not_a_copy",
        ),
    )
    op.create_index("ix_family_address_version_tree_id", "family_address_version", ["tree_id"])
    op.create_index(
        "ix_family_address_version_family",
        "family_address_version",
        ["tree_id", "family_address_id", "version"],
    )

    op.create_table(
        "family_address_version_source",
        *_audit_columns(),
        sa.Column("version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source_person_address_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tree_id", "version_id"],
            ["family_address_version.tree_id", "family_address_version.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "source_person_id"],
            ["person.tree_id", "person.id"],
            ondelete="SET NULL (source_person_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "source_person_address_id"],
            ["person_address.tree_id", "person_address.id"],
            ondelete="SET NULL (source_person_address_id)",
        ),
        sa.UniqueConstraint("tree_id", "id", name="uq_family_address_version_source_tree_id_id"),
        sa.UniqueConstraint("tree_id", "version_id", name="uq_family_address_version_source_version"),
    )
    op.create_index("ix_family_address_version_source_tree_id", "family_address_version_source", ["tree_id"])

    op.create_table(
        "family_address_version_ancestor",
        *_audit_columns(),
        sa.Column("descendant_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ancestor_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tree_id", "descendant_version_id"],
            ["family_address_version.tree_id", "family_address_version.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "ancestor_version_id"],
            ["family_address_version.tree_id", "family_address_version.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tree_id", "id", name="uq_family_address_version_ancestor_tree_id_id"),
        sa.UniqueConstraint(
            "tree_id",
            "descendant_version_id",
            "ancestor_version_id",
            name="uq_family_address_version_ancestor_pair",
        ),
        sa.CheckConstraint(
            "descendant_version_id <> ancestor_version_id",
            name="ck_family_address_version_ancestor_distinct_versions",
        ),
    )
    op.create_index(
        "ix_family_address_version_ancestor_tree_id", "family_address_version_ancestor", ["tree_id"]
    )
    op.create_index(
        "ix_family_address_ancestor_descendant",
        "family_address_version_ancestor",
        ["tree_id", "descendant_version_id"],
    )

    op.create_table(
        "family_address_release_consent",
        *_audit_columns(),
        sa.Column("source_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("destination_family_address_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consenting_controller_membership_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("permitted_privacy_level", _record_privacy(), nullable=False),
        sa.Column("audience_branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("purpose", sa.String(300), nullable=False),
        sa.Column("notice_version", sa.String(80), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tree_id", "source_version_id"],
            ["family_address_version.tree_id", "family_address_version.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "destination_family_address_id"],
            ["family_address.tree_id", "family_address.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "consenting_controller_membership_id"],
            ["tree_membership.tree_id", "tree_membership.id"],
            ondelete="SET NULL (consenting_controller_membership_id)",
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "audience_branch_id"],
            ["family_branch.tree_id", "family_branch.id"],
            ondelete="SET NULL (audience_branch_id)",
        ),
        sa.UniqueConstraint("tree_id", "id", name="uq_family_address_release_consent_tree_id_id"),
        sa.UniqueConstraint(
            "tree_id", "source_version_id", "destination_family_address_id", name="uq_family_address_release"
        ),
    )
    op.create_index(
        "ix_family_address_release_consent_tree_id", "family_address_release_consent", ["tree_id"]
    )

    reuse_mode = sa.Enum(
        "link", "copy", name="addressreusemode", native_enum=False, create_constraint=True, length=40
    )
    op.add_column("person_address", sa.Column("reuse_mode", reuse_mode, nullable=True))
    op.add_column("person_address", sa.Column("source_revoked_at", sa.DateTime(timezone=True), nullable=True))
    for column in (
        "linked_family_address_version_id",
        "source_family_address_version_id",
        "root_source_family_address_version_id",
        "ancestral_assertion_id",
        "copied_from_person_address_id",
    ):
        op.add_column("person_address", sa.Column(column, postgresql.UUID(as_uuid=True), nullable=True))
    for column, constraint_name in (
        ("linked_family_address_version_id", "fk_person_addr_link_family_version"),
        ("source_family_address_version_id", "fk_person_addr_source_family_version"),
        ("root_source_family_address_version_id", "fk_person_addr_root_family_version"),
    ):
        op.create_foreign_key(
            constraint_name,
            "person_address",
            "family_address_version",
            ["tree_id", column],
            ["tree_id", "id"],
            ondelete=f"SET NULL ({column})",
        )
    op.create_foreign_key(
        "fk_person_addr_ancestral_assertion",
        "person_address",
        "assertion",
        ["tree_id", "ancestral_assertion_id"],
        ["tree_id", "id"],
        ondelete="SET NULL (ancestral_assertion_id)",
    )
    op.create_foreign_key(
        "fk_person_addr_copied_from",
        "person_address",
        "person_address",
        ["tree_id", "copied_from_person_address_id"],
        ["tree_id", "id"],
        ondelete="SET NULL (copied_from_person_address_id)",
    )
    op.create_check_constraint(
        "ck_person_address_one_family_address_reuse_source",
        "person_address",
        "NOT (linked_family_address_version_id IS NOT NULL AND source_family_address_version_id IS NOT NULL)",
    )

    for table in (
        "family_address",
        "family_address_version",
        "family_address_version_source",
        "family_address_version_ancestor",
        "family_address_release_consent",
    ):
        for statement in enable_sql(table):
            op.execute(statement)


def downgrade() -> None:
    refuse_lossy_downgrades(
        LossyDowngrade(
            revision=revision,
            subject="reusable family addresses",
            losses={
                "family addresses and immutable versions (they would be deleted)": (
                    "SELECT count(*) FROM family_address"
                ),
                "address reuse links/copies (their policy ceilings would be forgotten)": """
                    SELECT count(*) FROM person_address
                    WHERE reuse_mode IS NOT NULL
                       OR linked_family_address_version_id IS NOT NULL
                       OR source_family_address_version_id IS NOT NULL
                       OR root_source_family_address_version_id IS NOT NULL
                       OR ancestral_assertion_id IS NOT NULL
                       OR copied_from_person_address_id IS NOT NULL
                       OR source_revoked_at IS NOT NULL
                """,
                "family-address grants (selected members would lose access)": (
                    "SELECT count(*) FROM access_grant WHERE resource_type = 'family_address'"
                ),
            },
        ),
        runbook="docs/operations/backup-restore-runbook.md",
    )
    for table in (
        "family_address_release_consent",
        "family_address_version_ancestor",
        "family_address_version_source",
        "family_address_version",
        "family_address",
    ):
        for statement in disable_sql(table):
            op.execute(statement)
    op.drop_constraint("ck_person_address_one_family_address_reuse_source", "person_address", type_="check")
    for name in (
        "fk_person_addr_copied_from",
        "fk_person_addr_ancestral_assertion",
        "fk_person_addr_root_family_version",
        "fk_person_addr_source_family_version",
        "fk_person_addr_link_family_version",
    ):
        op.drop_constraint(name, "person_address", type_="foreignkey")
    for column in (
        "copied_from_person_address_id",
        "ancestral_assertion_id",
        "root_source_family_address_version_id",
        "source_family_address_version_id",
        "linked_family_address_version_id",
        "reuse_mode",
        "source_revoked_at",
    ):
        op.drop_column("person_address", column)
    op.drop_table("family_address_release_consent")
    op.drop_table("family_address_version_ancestor")
    op.drop_table("family_address_version_source")
    op.drop_table("family_address_version")
    op.drop_table("family_address")
    grant_check = op.f("ck_access_grant_grantresource")
    op.drop_constraint(grant_check, "access_grant", type_="check")
    op.create_check_constraint(
        grant_check,
        "access_grant",
        "resource_type IN ('person', 'document', 'property', 'tradition', 'collection')",
    )
