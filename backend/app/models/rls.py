"""PostgreSQL row-level security for tree-scoped tables (ADR-0002 §defence in depth).

Every table below gets ``ENABLE ROW LEVEL SECURITY`` and a policy restricting rows to the tree bound
for the current transaction (``app.tree_id``; see ``app.core.db.bind_tree``). With no tree bound the
policy matches nothing — access fails closed.

Roles: the application connects as a *non-owner* role (e.g. ``vanshavali_app``) and is therefore
subject to the policies. Migrations and maintenance tools connect as the table owner, which RLS does
not restrict (policies are not FORCEd), so migrations, backups and bulk tooling keep working.

Identity/control tables that must be read before a tree is known — ``tree``, ``tree_membership``,
``tree_invitation``, ``profile_claim_invite``, ``app_user``, ``user_session``, ``auth_token``,
``external_identity`` — and the
append-only ``audit_event`` are not covered; they are protected by the service layer (and their own
rules). The two invite tables are resolved by a 256-bit token before the holder is a member; the
handler then binds the invite's tree for everything else it reads.
"""

from __future__ import annotations

from sqlalchemy import DDL, Table, event

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

POLICY_NAME = "tree_isolation"
_PREDICATE = "tree_id = nullif(current_setting('app.tree_id', true), '')::uuid"


def enable_sql(table: str) -> list[str]:
    return [
        f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY",
        f"CREATE POLICY {POLICY_NAME} ON {table} USING ({_PREDICATE}) WITH CHECK ({_PREDICATE})",
    ]


def disable_sql(table: str) -> list[str]:
    return [
        f"DROP POLICY IF EXISTS {POLICY_NAME} ON {table}",
        f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY",
    ]


GRANT_APP_ROLE_SQL = """
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA public TO {role}';
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}';
    EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role}';
  END IF;
END
$$;
"""


def attach_to_metadata(tables: dict[str, Table]) -> None:
    """Make ``metadata.create_all`` (used by fast tests) install the same policies as the migration."""
    for name in RLS_TABLES:
        table = tables[name]
        for stmt in enable_sql(name):
            event.listen(table, "after_create", DDL(stmt))
