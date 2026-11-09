"""record audiences and content owners

Revision ID: b5e8d1f3a2c6
Revises: 9c4e2a7d5b18
Create Date: 2026-11-09

ADR-0027 §1, §2 and §12.1, §12.3, §12.4.

- ``PrivacyLevel`` gains ``ONLY_ME`` and ``SELECTED_MEMBERS``. Every column that stores a privacy
  level shares the enum's CHECK, so all of them are widened; the API refuses the two values on
  anything that is not a shareable record (people, field groups, events, properties, ...).
- ``GrantResource`` gains ``tradition`` so a tradition entry can be shared with selected members.
- ``document`` and ``tradition_entry`` gain ``owner_membership_id`` (the content owner) and
  ``pending_owner_membership_id`` (a transfer offered but not accepted), both composite FKs to
  ``tree_membership`` with ``ON DELETE SET NULL``. The owner is backfilled from ``created_by`` where
  that user is still a member; otherwise the record has no owner (orphaned, §2).
- ``document`` gains ``audience_branch_id`` (composite FK to ``family_branch``, SET NULL): the
  branch a ``FAMILY_BRANCH`` document is shared with. A tradition entry's existing ``branch_id``
  already plays this role.
- Nothing is converted: legacy ``CUSTOM`` and ``PRIVATE_SELF`` records keep their meaning.

Downgrade maps ``ONLY_ME`` to ``PRIVATE_SELF`` and ``SELECTED_MEMBERS`` to ``CUSTOM`` (the nearest
existing levels), deletes tradition grants, narrows the CHECKs and drops the new columns.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b5e8d1f3a2c6"
down_revision: str | None = "9c4e2a7d5b18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_LEVELS = (
    "PRIVATE_SELF",
    "PRIVATE_TREE_ADMINS",
    "FAMILY_BRANCH",
    "TREE_MEMBERS",
    "INVITED_RESEARCHER",
    "PUBLIC_DECEASED_ONLY",
    "CUSTOM",
)
_NEW_LEVELS = (*_OLD_LEVELS, "ONLY_ME", "SELECTED_MEMBERS")

# (table, column, CHECK constraint name) for every column storing a PrivacyLevel
_LEVEL_COLUMNS = (
    ("tree", "default_person_privacy", "ck_tree_default_person_privacy"),
    ("document", "privacy_level", "ck_document_privacylevel"),
    ("person", "privacy_level", "ck_person_privacylevel"),
    ("place", "coordinate_privacy", "ck_place_coordinate_privacy"),
    ("event", "privacy_level", "ck_event_privacylevel"),
    ("profile_claim", "restore_privacy_level", "ck_profile_claim_restore_privacy_level"),
    ("property", "privacy_level", "ck_property_privacylevel"),
    ("source", "privacy_level", "ck_source_privacylevel"),
    ("assertion", "privacy_level", "ck_assertion_privacylevel"),
    ("astrology_profile", "privacy_level", "ck_astrology_profile_privacylevel"),
    ("tradition_entry", "privacy_level", "ck_tradition_entry_tradition_privacy_level"),
)

_OLD_RESOURCES = ("person", "document", "property")
_NEW_RESOURCES = (*_OLD_RESOURCES, "tradition")

_OWNED = ("document", "tradition_entry")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _set_checks(levels: Sequence[str], resources: Sequence[str]) -> None:
    for table, column, name in _LEVEL_COLUMNS:
        op.drop_constraint(op.f(name), table, type_="check")
        op.create_check_constraint(op.f(name), table, _in(column, levels))
    op.drop_constraint(op.f("ck_access_grant_grantresource"), "access_grant", type_="check")
    op.create_check_constraint(
        op.f("ck_access_grant_grantresource"), "access_grant", _in("resource_type", resources)
    )


def upgrade() -> None:
    _set_checks(_NEW_LEVELS, _NEW_RESOURCES)
    for table in _OWNED:
        op.add_column(table, sa.Column("owner_membership_id", sa.UUID(), nullable=True))
        op.add_column(table, sa.Column("pending_owner_membership_id", sa.UUID(), nullable=True))
        for column in ("owner_membership_id", "pending_owner_membership_id"):
            op.create_foreign_key(
                op.f(f"fk_{table}_tree_id_{column}_tree_membership"),
                table,
                "tree_membership",
                ["tree_id", column],
                ["tree_id", "id"],
                ondelete=f"SET NULL ({column})",
            )
        op.execute(
            f"""
            UPDATE {table} r SET owner_membership_id = m.id
            FROM tree_membership m
            WHERE m.tree_id = r.tree_id AND m.user_id = r.created_by
            """
        )
    op.add_column("document", sa.Column("audience_branch_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        op.f("fk_document_tree_id_audience_branch_id_family_branch"),
        "document",
        "family_branch",
        ["tree_id", "audience_branch_id"],
        ["tree_id", "id"],
        ondelete="SET NULL (audience_branch_id)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_document_tree_id_audience_branch_id_family_branch"), "document", type_="foreignkey")
    op.drop_column("document", "audience_branch_id")
    for table in _OWNED:
        for column in ("owner_membership_id", "pending_owner_membership_id"):
            op.drop_constraint(op.f(f"fk_{table}_tree_id_{column}_tree_membership"), table, type_="foreignkey")
            op.drop_column(table, column)
    for table, column, _name in _LEVEL_COLUMNS:
        op.execute(f"UPDATE {table} SET {column} = 'PRIVATE_SELF' WHERE {column} = 'ONLY_ME'")
        op.execute(f"UPDATE {table} SET {column} = 'CUSTOM' WHERE {column} = 'SELECTED_MEMBERS'")
    op.execute("DELETE FROM access_grant WHERE resource_type = 'tradition'")
    _set_checks(_OLD_LEVELS, _OLD_RESOURCES)
