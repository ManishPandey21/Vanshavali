"""PostgreSQL row-level security for tree-scoped tables (ADR-0002 §defence in depth).

Every table below gets ``ENABLE ROW LEVEL SECURITY`` and a policy restricting rows to the tree bound
for the current transaction (``app.tree_id``; see ``app.core.db.bind_tree``). With no tree bound the
policy matches nothing — access fails closed.

Roles: the application connects as a *non-owner* role (e.g. ``vanshavali_app``) and is therefore
subject to the policies. Migrations and maintenance tools connect as the table owner, which RLS does
not restrict (policies are not FORCEd), so migrations, backups and bulk tooling keep working.

Identity/control tables that must be read before a tree is known — ``tree``, ``tree_membership``,
``tree_invitation``, ``profile_claim_invite``, ``app_user``, ``user_session``, ``auth_token``,
``external_identity``, ``notification_contact`` (a user's own phone numbers) — and the
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
    "change_proposal",
    "change_proposal_item",
    "chart_preset",
    "citation",
    "consent_record",
    "document",
    "document_derivative",
    "document_link",
    "document_metadata_version",
    "event",
    "event_media",
    "event_participant",
    "event_reminder",
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
    "notification_delivery",
    "notification_preference",
    "person",
    "place",
    "profile_claim",
    "property",
    "property_event",
    "property_event_parcel",
    "property_interest",
    "proposal_citation",
    "proposal_comment",
    "record_revision",
    "relationship",
    "relative_age_order",
    "render_artifact",
    "render_job",
    "source",
    "tree_vocabulary_term",
    "user_notification",
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


# Global reference data the application only reads (ADR-0019 §2): loaded by operator CLIs as the
# schema owner. The grant below revokes write access on these, whenever they exist.
READ_ONLY_TABLES: tuple[str, ...] = ("geo_snapshot", "geo_unit", "geo_unit_alias", "pincode_office")

# (the array below must list READ_ONLY_TABLES; tests/test_geo.py checks that it does). No "%" in
# this SQL: ensure_app_role sends it through the driver, where "%" starts a placeholder.
GRANT_APP_ROLE_SQL = """
DO $$
DECLARE
  t text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
    EXECUTE 'GRANT USAGE ON SCHEMA public TO {role}';
    EXECUTE 'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}';
    EXECUTE 'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}';
    EXECUTE 'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role}';
    FOREACH t IN ARRAY ARRAY['geo_snapshot', 'geo_unit', 'geo_unit_alias', 'pincode_office'] LOOP
      IF to_regclass('public.' || t) IS NOT NULL THEN
        EXECUTE 'REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ' || quote_ident(t) || ' FROM {role}';
      END IF;
    END LOOP;
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
