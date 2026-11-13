from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import Boolean, CheckConstraint, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TreeScopedMixin, enum_column, tree_fk, tree_unique
from app.models.enums import RecordPrivacyLevel


class FamilyAddress(TreeScopedMixin, Base):
    """A reusable family postal record; it is not evidence of property ownership."""

    __tablename__ = "family_address"
    __table_args__ = (
        tree_unique("family_address"),
        tree_fk(["controller_membership_id"], "tree_membership", ondelete="SET NULL"),
        tree_fk(["audience_branch_id"], "family_branch", ondelete="SET NULL"),
        tree_fk(["branch_id"], "family_branch", ondelete="SET NULL"),
        tree_fk(["household_id"], "household", ondelete="SET NULL"),
        tree_fk(["property_id"], "property", ondelete="SET NULL"),
        tree_fk(["place_id"], "place", ondelete="SET NULL"),
        tree_fk(["ancestral_assertion_id"], "assertion", ondelete="SET NULL"),
        UniqueConstraint(
            "tree_id", "controller_membership_id", "idempotency_key", name="uq_family_address_idempotency"
        ),
        Index("ix_family_address_branch", "tree_id", "branch_id"),
        Index("ix_family_address_place", "tree_id", "place_id"),
    )

    label: Mapped[str] = mapped_column(String(200))
    controller_membership_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    privacy_level: Mapped[RecordPrivacyLevel] = mapped_column(enum_column(RecordPrivacyLevel))
    audience_branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    household_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    property_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    place_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ancestral_assertion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    current_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    revision: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    sharing_released: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    idempotency_key: Mapped[str | None] = mapped_column(String(100))
    retired_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class FamilyAddressVersion(TreeScopedMixin, Base):
    """Immutable encrypted snapshot of one family-address revision."""

    __tablename__ = "family_address_version"
    __table_args__ = (
        tree_unique("family_address_version"),
        tree_fk(["family_address_id"], "family_address"),
        tree_fk(["place_id"], "place", ondelete="SET NULL"),
        tree_fk(["source_ancestral_assertion_id"], "assertion", ondelete="SET NULL"),
        tree_fk(["root_source_version_id"], "family_address_version", ondelete="SET NULL"),
        UniqueConstraint("tree_id", "family_address_id", "version", name="uq_family_address_version_number"),
        CheckConstraint(
            "source_ancestral_assertion_id IS NULL OR root_source_version_id IS NULL",
            name="ancestral_source_is_not_a_copy",
        ),
        Index("ix_family_address_version_family", "tree_id", "family_address_id", "version"),
    )

    family_address_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    version: Mapped[int] = mapped_column(Integer)
    place_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    locality: Mapped[str | None] = mapped_column(String(200))
    sub_district: Mapped[str | None] = mapped_column(String(160))
    district: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(2))
    payload_enc: Mapped[str] = mapped_column(Text)
    source_ancestral_assertion_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    root_source_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reason_enc: Mapped[str | None] = mapped_column(Text)


class FamilyAddressVersionSource(TreeScopedMixin, Base):
    """Cycle-safe provenance tombstone for a version copied from a person's address."""

    __tablename__ = "family_address_version_source"
    __table_args__ = (
        tree_unique("family_address_version_source"),
        tree_fk(["version_id"], "family_address_version"),
        tree_fk(["source_person_id"], "person", ondelete="SET NULL"),
        tree_fk(["source_person_address_id"], "person_address", ondelete="SET NULL"),
        UniqueConstraint("tree_id", "version_id", name="uq_family_address_version_source_version"),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    source_person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_person_address_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class FamilyAddressVersionAncestor(TreeScopedMixin, Base):
    """Every policy ceiling in a copied version's chain, not only its immediate parent."""

    __tablename__ = "family_address_version_ancestor"
    __table_args__ = (
        tree_unique("family_address_version_ancestor"),
        tree_fk(["descendant_version_id"], "family_address_version"),
        tree_fk(["ancestor_version_id"], "family_address_version"),
        UniqueConstraint(
            "tree_id",
            "descendant_version_id",
            "ancestor_version_id",
            name="uq_family_address_version_ancestor_pair",
        ),
        CheckConstraint("descendant_version_id <> ancestor_version_id", name="distinct_versions"),
        Index("ix_family_address_ancestor_descendant", "tree_id", "descendant_version_id"),
    )

    descendant_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    ancestor_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))


class FamilyAddressReleaseConsent(TreeScopedMixin, Base):
    """Explicit controller consent for a copied address to gain an independent audience."""

    __tablename__ = "family_address_release_consent"
    __table_args__ = (
        tree_unique("family_address_release_consent"),
        tree_fk(["source_version_id"], "family_address_version"),
        tree_fk(["destination_family_address_id"], "family_address"),
        tree_fk(["consenting_controller_membership_id"], "tree_membership", ondelete="SET NULL"),
        tree_fk(["audience_branch_id"], "family_branch", ondelete="SET NULL"),
        UniqueConstraint(
            "tree_id", "source_version_id", "destination_family_address_id", name="uq_family_address_release"
        ),
    )

    source_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    destination_family_address_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    consenting_controller_membership_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    permitted_privacy_level: Mapped[RecordPrivacyLevel] = mapped_column(enum_column(RecordPrivacyLevel))
    audience_branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    purpose: Mapped[str] = mapped_column(String(300))
    notice_version: Mapped[str] = mapped_column(String(80))
    granted_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    withdrawn_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
