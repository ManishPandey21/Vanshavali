"""Standalone photo collections (ADR-0027 §6, increment 4).

A collection is a shareable record of its own (owner membership, audience, grants). Its items point
at photos in the document vault; an item never changes the photo's own audience, and a viewer sees
an item only when they may see both the collection and the photo.
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TreeScopedMixin, enum_column, tree_fk, tree_unique
from app.models.enums import RecordPrivacyLevel


class PhotoCollection(TreeScopedMixin, Base):
    __tablename__ = "photo_collection"
    __table_args__ = (
        tree_unique("photo_collection"),
        tree_fk(["owner_membership_id"], "tree_membership", ondelete="SET NULL"),
        tree_fk(["audience_branch_id"], "family_branch", ondelete="SET NULL"),
    )

    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str | None] = mapped_column(Text)
    privacy_level: Mapped[RecordPrivacyLevel] = mapped_column(
        enum_column(RecordPrivacyLevel, "collection_privacy_level"),
        default=RecordPrivacyLevel.ONLY_ME,
        server_default=RecordPrivacyLevel.ONLY_ME.value,
    )
    owner_membership_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    audience_branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))


class PhotoCollectionItem(TreeScopedMixin, Base):
    __tablename__ = "photo_collection_item"
    __table_args__ = (
        tree_unique("photo_collection_item"),
        tree_fk(["collection_id"], "photo_collection"),
        tree_fk(["document_id"], "document"),
        UniqueConstraint("collection_id", "document_id", name="uq_photo_collection_item"),
        Index("ix_photo_collection_item_collection", "tree_id", "collection_id", "sort_order"),
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    caption: Mapped[str | None] = mapped_column(String(500))
    is_cover: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
