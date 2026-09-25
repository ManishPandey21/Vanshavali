"""row-level security on tree-scoped tables (second isolation barrier)

Revision ID: b7c1e0d2f3a4
Revises: a2e3647779fc
Create Date: 2026-09-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

from app.models.rls import GRANT_APP_ROLE_SQL, disable_sql, enable_sql

revision: str = "b7c1e0d2f3a4"
down_revision: str | None = "a2e3647779fc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "vanshavali_app"

# Frozen at this revision. A table that becomes tree-scoped later gets its own migration that calls
# enable_sql(); importing the live app.models.rls.RLS_TABLES here would break fresh upgrades.
RLS_TABLES: tuple[str, ...] = (
    "access_grant",
    "assertion",
    "astrology_profile",
    "branch_membership",
    "citation",
    "consent_record",
    "document",
    "document_derivative",
    "document_link",
    "document_metadata_version",
    "event",
    "event_participant",
    "export_job",
    "extraction_proposal",
    "family_branch",
    "family_data_attestation",
    "gedcom_extension",
    "household",
    "household_membership",
    "import_job",
    "land_parcel",
    "merge_record",
    "name_record",
    "person",
    "place",
    "profile_claim",
    "property",
    "property_event",
    "property_event_parcel",
    "property_interest",
    "relationship",
    "source",
)


def upgrade() -> None:
    for table in RLS_TABLES:
        for stmt in enable_sql(table):
            op.execute(stmt)
    # The application role (non-owner, subject to RLS) gets DML rights if it exists.
    op.execute(GRANT_APP_ROLE_SQL.format(role=APP_ROLE))


def downgrade() -> None:
    for table in RLS_TABLES:
        for stmt in disable_sql(table):
            op.execute(stmt)
