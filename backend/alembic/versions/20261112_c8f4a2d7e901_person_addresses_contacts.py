"""encrypted person addresses, history and contact methods (ADR-0031)

Revision ID: c8f4a2d7e901
Revises: e7c2a9f4b310
Create Date: 2026-11-12
"""

from __future__ import annotations

import datetime as dt
import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op
from app.core.encrypted_json import decrypt_json as _dec
from app.core.encrypted_json import encrypt_json as _enc
from app.core.ids import uuid7
from app.models.rls import disable_sql, enable_sql

revision: str = "c8f4a2d7e901"
down_revision: str | None = "e7c2a9f4b310"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _payload_aad(record_type: str, record_id: uuid.UUID) -> str:
    return f"person-{record_type}:{record_id}"


def _revision_aad(revision_id: uuid.UUID, side: str) -> str:
    return f"person-detail-revision:{revision_id}:{side}"


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


def upgrade() -> None:
    citation_target_check = op.f("ck_citation_citationtarget")
    op.drop_constraint(citation_target_check, "citation", type_="check")
    op.create_check_constraint(
        citation_target_check,
        "citation",
        "target_type IN ('person', 'name_record', 'event', 'relationship', 'assertion', "
        "'astrology_profile', 'property', 'land_parcel', 'property_interest', 'property_event', "
        "'household', 'tradition', 'address')",
    )
    address_purpose = sa.Enum(
        "unknown",
        "current_residence",
        "permanent",
        "previous_residence",
        "ancestral_home",
        "native_place",
        "correspondence",
        "other",
        name="addresspurpose",
        native_enum=False,
        create_constraint=True,
        length=40,
    )
    address_status = sa.Enum(
        "unknown",
        "current",
        "former",
        name="addressstatus",
        native_enum=False,
        create_constraint=True,
        length=40,
    )
    contact_kind = sa.Enum(
        "email",
        "mobile",
        "whatsapp",
        "telegram",
        "instagram",
        "legacy_note",
        name="contactkind",
        native_enum=False,
        create_constraint=True,
        length=40,
    )
    op.create_table(
        "person_address",
        *_audit_columns(),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("purpose", address_purpose, nullable=False),
        sa.Column("status", address_status, nullable=False),
        sa.Column("is_primary_current", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("place_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("locality", sa.String(200), nullable=True),
        sa.Column("sub_district", sa.String(160), nullable=True),
        sa.Column("district", sa.String(120), nullable=True),
        sa.Column("state", sa.String(120), nullable=True),
        sa.Column("country_code", sa.String(2), nullable=True),
        sa.Column("payload_enc", sa.Text(), nullable=False),
        sa.Column("valid_from", postgresql.JSONB(), nullable=True),
        sa.Column("valid_until", postgresql.JSONB(), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("source", sa.String(40), server_default="manual", nullable=False),
        sa.Column("legacy_imported", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tree_id", "person_id"], ["person.tree_id", "person.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "place_id"], ["place.tree_id", "place.id"], ondelete="SET NULL (place_id)"
        ),
        sa.UniqueConstraint("tree_id", "id", name="uq_person_address_tree_id_id"),
        sa.UniqueConstraint("tree_id", "person_id", "idempotency_key", name="uq_person_address_idempotency"),
        sa.CheckConstraint(
            "NOT is_primary_current OR (status = 'current' AND withdrawn_at IS NULL)",
            name="ck_person_address_primary_is_current",
        ),
    )
    op.create_index("ix_person_address_tree_id", "person_address", ["tree_id"])
    op.create_index("ix_person_address_person", "person_address", ["tree_id", "person_id"])
    op.create_index(
        "ix_person_address_person_purpose",
        "person_address",
        ["tree_id", "person_id", "purpose"],
    )
    op.create_index(
        "uq_person_address_active_legacy",
        "person_address",
        ["tree_id", "person_id"],
        unique=True,
        postgresql_where=sa.text("legacy_imported AND withdrawn_at IS NULL"),
    )
    op.create_index(
        "uq_person_address_primary_current",
        "person_address",
        ["tree_id", "person_id"],
        unique=True,
        postgresql_where=sa.text("is_primary_current AND withdrawn_at IS NULL"),
    )

    op.create_table(
        "person_contact_method",
        *_audit_columns(),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", contact_kind, nullable=False),
        sa.Column("value_enc", sa.Text(), nullable=False),
        sa.Column("value_hint", sa.String(160), nullable=False),
        sa.Column("purpose", sa.String(80), nullable=True),
        sa.Column("language", sa.String(16), nullable=True),
        sa.Column("is_preferred", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("copied_from_contact_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("copied_from_revision", sa.Integer(), nullable=True),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("source", sa.String(40), server_default="manual", nullable=False),
        sa.Column("legacy_imported", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["tree_id", "person_id"], ["person.tree_id", "person.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["tree_id", "copied_from_contact_id"],
            ["person_contact_method.tree_id", "person_contact_method.id"],
            ondelete="SET NULL (copied_from_contact_id)",
        ),
        sa.UniqueConstraint("tree_id", "id", name="uq_person_contact_method_tree_id_id"),
        sa.UniqueConstraint("tree_id", "person_id", "idempotency_key", name="uq_person_contact_idempotency"),
    )
    op.create_index("ix_person_contact_method_tree_id", "person_contact_method", ["tree_id"])
    op.create_index("ix_person_contact_person", "person_contact_method", ["tree_id", "person_id"])
    op.create_index(
        "uq_person_contact_active_legacy",
        "person_contact_method",
        ["tree_id", "person_id"],
        unique=True,
        postgresql_where=sa.text("legacy_imported AND withdrawn_at IS NULL"),
    )
    op.create_index(
        "uq_person_contact_preferred",
        "person_contact_method",
        ["tree_id", "person_id", "kind"],
        unique=True,
        postgresql_where=sa.text("is_preferred AND withdrawn_at IS NULL"),
    )

    op.create_table(
        "person_detail_revision",
        *_audit_columns(),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("record_type", sa.String(20), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("operation", sa.String(20), nullable=False),
        sa.Column("reason_enc", sa.Text(), nullable=True),
        sa.Column("before_enc", sa.Text(), nullable=True),
        sa.Column("after_enc", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["tree_id", "person_id"], ["person.tree_id", "person.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("tree_id", "id", name="uq_person_detail_revision_tree_id_id"),
        sa.UniqueConstraint(
            "tree_id", "record_type", "record_id", "revision", name="uq_person_detail_revision"
        ),
    )
    op.create_index("ix_person_detail_revision_tree_id", "person_detail_revision", ["tree_id"])
    op.create_index(
        "ix_person_detail_revision_record", "person_detail_revision", ["tree_id", "record_type", "record_id"]
    )

    for table in ("person_address", "person_contact_method", "person_detail_revision"):
        for statement in enable_sql(table):
            op.execute(statement)

    connection = op.get_bind()
    people = connection.execute(
        sa.text(
            "SELECT id, tree_id, created_by, residential_address, contact_info FROM person WHERE residential_address IS NOT NULL OR contact_info IS NOT NULL"
        )
    ).mappings()
    now = dt.datetime.now(dt.UTC)
    for person in people:
        if person["residential_address"] is not None:
            row_id, rev_id = uuid7(), uuid7()
            snapshot = {
                "id": str(row_id),
                "person_id": str(person["id"]),
                "purpose": "unknown",
                "status": "unknown",
                "is_primary_current": False,
                "place_id": None,
                "locality": None,
                "sub_district": None,
                "district": None,
                "state": None,
                "country_code": None,
                "postal_code": None,
                "valid_from": None,
                "valid_until": None,
                "building": None,
                "street": None,
                "landmark": None,
                "notes": None,
                "as_recorded": person["residential_address"],
            }
            connection.execute(
                sa.text(
                    "INSERT INTO person_address (id, tree_id, person_id, purpose, status, is_primary_current, payload_enc, revision, source, legacy_imported, created_by, updated_by, created_at, updated_at) VALUES (:id, :tree, :person, 'unknown', 'unknown', false, :payload, 1, 'legacy_profile', true, :user, :user, :now, :now)"
                ),
                {
                    "id": row_id,
                    "tree": person["tree_id"],
                    "person": person["id"],
                    "payload": _enc(
                        {
                            "building": None,
                            "street": None,
                            "landmark": None,
                            "notes": None,
                            "as_recorded": person["residential_address"],
                            "postal_code": None,
                            "gram_panchayat": None,
                            "post_office": None,
                        },
                        _payload_aad("address", row_id),
                    ),
                    "user": person["created_by"],
                    "now": now,
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO person_detail_revision (id, tree_id, person_id, record_type, record_id, revision, operation, after_enc, created_by, updated_by, created_at, updated_at) VALUES (:id, :tree, :person, 'address', :record, 1, 'legacy_imported', :after, :user, :user, :now, :now)"
                ),
                {
                    "id": rev_id,
                    "tree": person["tree_id"],
                    "person": person["id"],
                    "record": row_id,
                    "after": _enc(snapshot, _revision_aad(rev_id, "after")),
                    "user": person["created_by"],
                    "now": now,
                },
            )
        if person["contact_info"] is not None:
            row_id, rev_id = uuid7(), uuid7()
            snapshot = {
                "id": str(row_id),
                "person_id": str(person["id"]),
                "kind": "legacy_note",
                "value": person["contact_info"],
                "purpose": None,
                "language": None,
                "is_preferred": False,
            }
            connection.execute(
                sa.text(
                    "INSERT INTO person_contact_method (id, tree_id, person_id, kind, value_enc, value_hint, revision, source, legacy_imported, created_by, updated_by, created_at, updated_at) VALUES (:id, :tree, :person, 'legacy_note', :value, 'Legacy contact note', 1, 'legacy_profile', true, :user, :user, :now, :now)"
                ),
                {
                    "id": row_id,
                    "tree": person["tree_id"],
                    "person": person["id"],
                    "value": _enc({"value": person["contact_info"]}, _payload_aad("contact", row_id)),
                    "user": person["created_by"],
                    "now": now,
                },
            )
            connection.execute(
                sa.text(
                    "INSERT INTO person_detail_revision (id, tree_id, person_id, record_type, record_id, revision, operation, after_enc, created_by, updated_by, created_at, updated_at) VALUES (:id, :tree, :person, 'contact', :record, 1, 'legacy_imported', :after, :user, :user, :now, :now)"
                ),
                {
                    "id": rev_id,
                    "tree": person["tree_id"],
                    "person": person["id"],
                    "record": row_id,
                    "after": _enc(snapshot, _revision_aad(rev_id, "after")),
                    "user": person["created_by"],
                    "now": now,
                },
            )
    connection.execute(
        sa.text(
            "UPDATE person SET residential_address = NULL, contact_info = NULL WHERE residential_address IS NOT NULL OR contact_info IS NOT NULL"
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    unsafe = connection.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM person_address WHERE NOT legacy_imported OR withdrawn_at IS NOT NULL OR revision <> 1) + "
            "(SELECT count(*) FROM person_contact_method WHERE NOT legacy_imported OR withdrawn_at IS NOT NULL OR revision <> 1) + "
            "(SELECT count(*) FROM citation WHERE target_type = 'address')"
        )
    ).scalar_one()
    if unsafe:
        raise RuntimeError(
            f"Refusing downgrade: {unsafe} address/contact rows cannot be represented in legacy profile fields"
        )
    for row in connection.execute(
        sa.text("SELECT person_id, id, payload_enc FROM person_address WHERE legacy_imported")
    ).mappings():
        value = _dec(row["payload_enc"], _payload_aad("address", row["id"])).get("as_recorded")
        connection.execute(
            sa.text("UPDATE person SET residential_address = :value WHERE id = :id"),
            {"value": value, "id": row["person_id"]},
        )
    for row in connection.execute(
        sa.text("SELECT person_id, id, value_enc FROM person_contact_method WHERE legacy_imported")
    ).mappings():
        value = _dec(row["value_enc"], _payload_aad("contact", row["id"])).get("value")
        connection.execute(
            sa.text("UPDATE person SET contact_info = :value WHERE id = :id"),
            {"value": value, "id": row["person_id"]},
        )
    for table in ("person_detail_revision", "person_contact_method", "person_address"):
        for statement in disable_sql(table):
            op.execute(statement)
        op.drop_table(table)
    citation_target_check = op.f("ck_citation_citationtarget")
    op.drop_constraint(citation_target_check, "citation", type_="check")
    op.create_check_constraint(
        citation_target_check,
        "citation",
        "target_type IN ('person', 'name_record', 'event', 'relationship', 'assertion', "
        "'astrology_profile', 'property', 'land_parcel', 'property_interest', 'property_event', "
        "'household', 'tradition')",
    )
