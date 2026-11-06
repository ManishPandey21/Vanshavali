from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from pydantic import Field

from app.api.schemas import ApiModel
from app.core.dates import GenealogicalDate
from app.models.enums import DescentRule, HouseholdRole
from app.modules.genealogy.schemas import PersonSummary


class BranchIn(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    founder_person_id: uuid.UUID | None = None
    parent_branch_id: uuid.UUID | None = None
    descent_rule: DescentRule = DescentRule.BILATERAL


class BranchUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    founder_person_id: uuid.UUID | None = None
    parent_branch_id: uuid.UUID | None = None
    descent_rule: DescentRule | None = None


class BranchOut(ApiModel):
    id: uuid.UUID
    name: str
    description: str | None
    founder_person_id: uuid.UUID | None
    parent_branch_id: uuid.UUID | None
    descent_rule: DescentRule
    # pending provisional people (ADR-0020 §8) are never in member_count; this counts the ones the
    # viewer can see, and is 0 for everyone else
    member_count: int = 0
    provisional_member_count: int = 0
    created_at: dt.datetime


class BranchMemberOut(ApiModel):
    person: PersonSummary | None
    hidden: bool = False
    basis: str


class BranchDetailOut(BranchOut):
    members: list[BranchMemberOut] = []
    hidden_member_count: int = 0


class BranchMembersIn(ApiModel):
    person_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class DeriveOut(ApiModel):
    added: int
    total: int


class HouseholdIn(ApiModel):
    name: str = Field(min_length=1, max_length=200)
    house_name: str | None = Field(default=None, max_length=200)
    place_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    start_date: GenealogicalDate | None = None
    end_date: GenealogicalDate | None = None
    notes: str | None = Field(default=None, max_length=5000)


class HouseholdUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    house_name: str | None = None
    place_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    start_date: GenealogicalDate | None = None
    end_date: GenealogicalDate | None = None
    notes: str | None = None


class HouseholdMemberIn(ApiModel):
    person_id: uuid.UUID
    role: HouseholdRole = HouseholdRole.MEMBER
    start_date: GenealogicalDate | None = None
    end_date: GenealogicalDate | None = None


class HouseholdMemberOut(ApiModel):
    id: uuid.UUID
    person: PersonSummary | None
    hidden: bool = False
    role: HouseholdRole
    start_date: dict[str, Any] | None
    end_date: dict[str, Any] | None
    current: bool = True


class HouseholdOut(ApiModel):
    id: uuid.UUID
    name: str
    house_name: str | None
    place_id: uuid.UUID | None
    place_name: str | None = None
    branch_id: uuid.UUID | None
    start_date: dict[str, Any] | None
    end_date: dict[str, Any] | None
    notes: str | None
    # pending provisional people (ADR-0020 §8) are never in member_count; this counts the ones the
    # viewer can see, and is 0 for everyone else
    member_count: int = 0
    provisional_member_count: int = 0
    created_at: dt.datetime


class HouseholdDetailOut(HouseholdOut):
    members: list[HouseholdMemberOut] = []
    hidden_member_count: int = 0


class PersonHouseholdOut(ApiModel):
    household: HouseholdOut
    role: HouseholdRole
    start_date: dict[str, Any] | None
    end_date: dict[str, Any] | None
