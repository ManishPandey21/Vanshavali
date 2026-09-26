"""claim invite decline and removal requests

Revision ID: edcd174a0123
Revises: c4e8f1a2b3d5
Create Date: 2026-09-26

ADR-0011 amendment: "this isn't me" (invite declined_at) and "this is me, remove me" (profile_claim
kind = removal, with the privacy level to restore if an admin declines the request).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "edcd174a0123"
down_revision: str | None = "c4e8f1a2b3d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LEVELS = (
    "PRIVATE_SELF",
    "PRIVATE_TREE_ADMINS",
    "FAMILY_BRANCH",
    "TREE_MEMBERS",
    "INVITED_RESEARCHER",
    "PUBLIC_DECEASED_ONLY",
    "CUSTOM",
)


def upgrade() -> None:
    op.add_column(
        "profile_claim",
        sa.Column(
            "kind",
            sa.Enum(
                "claim", "removal", name="claimkind", native_enum=False, create_constraint=False, length=40
            ),
            server_default="claim",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_profile_claim_claimkind"), "profile_claim", "kind IN ('claim', 'removal')"
    )
    op.add_column(
        "profile_claim",
        sa.Column(
            "restore_privacy_level",
            sa.Enum(
                *_LEVELS, name="restore_privacy_level", native_enum=False, create_constraint=False, length=40
            ),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        op.f("ck_profile_claim_restore_privacy_level"),
        "profile_claim",
        "restore_privacy_level IN (" + ", ".join(f"'{v}'" for v in _LEVELS) + ")",
    )
    op.add_column("profile_claim_invite", sa.Column("declined_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("profile_claim_invite", "declined_at")
    op.drop_constraint(op.f("ck_profile_claim_restore_privacy_level"), "profile_claim", type_="check")
    op.drop_column("profile_claim", "restore_privacy_level")
    op.drop_constraint(op.f("ck_profile_claim_claimkind"), "profile_claim", type_="check")
    op.drop_column("profile_claim", "kind")
