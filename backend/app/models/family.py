from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TreeScopedMixin, enum_column, tree_fk, tree_unique
from app.models.enums import DescentRule, HouseholdRole


class FamilyBranch(TreeScopedMixin, Base):
    __tablename__ = "family_branch"
    __table_args__ = (
        tree_unique("family_branch"),
        tree_fk(["founder_person_id"], "person", ondelete="SET NULL"),
        tree_fk(["parent_branch_id"], "family_branch", ondelete="SET NULL"),
    )

    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    founder_person_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    parent_branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    descent_rule: Mapped[DescentRule] = mapped_column(
        enum_column(DescentRule), default=DescentRule.BILATERAL, server_default=DescentRule.BILATERAL.value
    )


class BranchMembership(TreeScopedMixin, Base):
    __tablename__ = "branch_membership"
    __table_args__ = (
        tree_unique("branch_membership"),
        tree_fk(["branch_id"], "family_branch"),
        tree_fk(["person_id"], "person"),
        UniqueConstraint("branch_id", "person_id", name="uq_branch_membership"),
        Index("ix_branch_membership_person", "tree_id", "person_id"),
    )

    branch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    basis: Mapped[str] = mapped_column(String(40), default="manual", server_default="manual")


class Household(TreeScopedMixin, Base):
    __tablename__ = "household"
    __table_args__ = (
        tree_unique("household"),
        tree_fk(["place_id"], "place", ondelete="SET NULL"),
        tree_fk(["branch_id"], "family_branch", ondelete="SET NULL"),
    )

    name: Mapped[str] = mapped_column(String(200))
    house_name: Mapped[str | None] = mapped_column(String(200))
    place_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    start_date: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    end_date: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)


class HouseholdMembership(TreeScopedMixin, Base):
    __tablename__ = "household_membership"
    __table_args__ = (
        tree_unique("household_membership"),
        tree_fk(["household_id"], "household"),
        tree_fk(["person_id"], "person"),
        Index("ix_household_membership_person", "tree_id", "person_id"),
    )

    household_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    person_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    role: Mapped[HouseholdRole] = mapped_column(enum_column(HouseholdRole), default=HouseholdRole.MEMBER)
    start_date: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    end_date: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
