from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TreeScopedMixin, enum_column, tree_fk, tree_unique
from app.models.enums import AddressPurpose, AddressReuseMode, AddressStatus, ContactKind


class PersonAddress(TreeScopedMixin, Base):
    __tablename__ = "person_address"
    __table_args__ = (
        tree_unique("person_address"),
        tree_fk(["person_id"], "person"),
        tree_fk(["place_id"], "place", ondelete="SET NULL"),
        tree_fk(
            ["linked_family_address_version_id"],
            "family_address_version",
            ondelete="SET NULL",
            name="fk_person_addr_link_family_version",
        ),
        tree_fk(
            ["source_family_address_version_id"],
            "family_address_version",
            ondelete="SET NULL",
            name="fk_person_addr_source_family_version",
        ),
        tree_fk(
            ["root_source_family_address_version_id"],
            "family_address_version",
            ondelete="SET NULL",
            name="fk_person_addr_root_family_version",
        ),
        tree_fk(
            ["ancestral_assertion_id"],
            "assertion",
            ondelete="SET NULL",
            name="fk_person_addr_ancestral_assertion",
        ),
        tree_fk(
            ["copied_from_person_address_id"],
            "person_address",
            ondelete="SET NULL",
            name="fk_person_addr_copied_from",
        ),
        UniqueConstraint("tree_id", "person_id", "idempotency_key", name="uq_person_address_idempotency"),
        CheckConstraint(
            "NOT is_primary_current OR (status = 'current' AND withdrawn_at IS NULL)",
            name="primary_is_current",
        ),
        CheckConstraint(
            "NOT (linked_family_address_version_id IS NOT NULL AND source_family_address_version_id IS NOT NULL)",
            name="one_family_address_reuse_source",
        ),
        Index("ix_person_address_person", "tree_id", "person_id"),
        Index("ix_person_address_person_purpose", "tree_id", "person_id", "purpose"),
        Index(
            "uq_person_address_active_legacy",
            "tree_id",
            "person_id",
            unique=True,
            postgresql_where=text("legacy_imported AND withdrawn_at IS NULL"),
        ),
        Index(
            "uq_person_address_primary_current",
            "tree_id",
            "person_id",
            unique=True,
            postgresql_where=text("is_primary_current AND withdrawn_at IS NULL"),
        ),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    purpose: Mapped[AddressPurpose] = mapped_column(enum_column(AddressPurpose))
    status: Mapped[AddressStatus] = mapped_column(enum_column(AddressStatus))
    is_primary_current: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    place_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    locality: Mapped[str | None] = mapped_column(String(200))
    sub_district: Mapped[str | None] = mapped_column(String(160))
    district: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(2))
    payload_enc: Mapped[str] = mapped_column(Text)
    valid_from: Mapped[dict | None] = mapped_column(JSONB)
    valid_until: Mapped[dict | None] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(40), default="manual", server_default="manual")
    reuse_mode: Mapped[AddressReuseMode | None] = mapped_column(enum_column(AddressReuseMode))
    linked_family_address_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_family_address_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    root_source_family_address_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ancestral_assertion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    copied_from_person_address_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_revoked_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    legacy_imported: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    withdrawn_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class PersonContactMethod(TreeScopedMixin, Base):
    __tablename__ = "person_contact_method"
    __table_args__ = (
        tree_unique("person_contact_method"),
        tree_fk(["person_id"], "person"),
        tree_fk(["copied_from_contact_id"], "person_contact_method", ondelete="SET NULL"),
        UniqueConstraint("tree_id", "person_id", "idempotency_key", name="uq_person_contact_idempotency"),
        Index("ix_person_contact_person", "tree_id", "person_id"),
        Index(
            "uq_person_contact_active_legacy",
            "tree_id",
            "person_id",
            unique=True,
            postgresql_where=text("legacy_imported AND withdrawn_at IS NULL"),
        ),
        Index(
            "uq_person_contact_preferred",
            "tree_id",
            "person_id",
            "kind",
            unique=True,
            postgresql_where=text("is_preferred AND withdrawn_at IS NULL"),
        ),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[ContactKind] = mapped_column(enum_column(ContactKind))
    value_enc: Mapped[str] = mapped_column(Text)
    value_hint: Mapped[str] = mapped_column(String(160))
    purpose: Mapped[str | None] = mapped_column(String(80))
    language: Mapped[str | None] = mapped_column(String(16))
    is_preferred: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    copied_from_contact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    copied_from_revision: Mapped[int | None] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    source: Mapped[str] = mapped_column(String(40), default="manual", server_default="manual")
    legacy_imported: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    withdrawn_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class PersonDetailRevision(TreeScopedMixin, Base):
    __tablename__ = "person_detail_revision"
    __table_args__ = (
        tree_unique("person_detail_revision"),
        tree_fk(["person_id"], "person"),
        UniqueConstraint("tree_id", "record_type", "record_id", "revision", name="uq_person_detail_revision"),
        Index("ix_person_detail_revision_record", "tree_id", "record_type", "record_id"),
    )

    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    record_type: Mapped[str] = mapped_column(String(20))
    record_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    revision: Mapped[int] = mapped_column(Integer)
    operation: Mapped[str] = mapped_column(String(20))
    reason_enc: Mapped[str | None] = mapped_column(Text)
    before_enc: Mapped[str | None] = mapped_column(Text)
    after_enc: Mapped[str | None] = mapped_column(Text)
