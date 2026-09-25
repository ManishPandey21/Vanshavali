from __future__ import annotations

import uuid

from fastapi import APIRouter, status
from sqlalchemy import func, select

from app.api.deps import TreeCtx
from app.api.schemas import ApiModel, Message
from app.core.dates import GenealogicalDate
from app.models import BranchMembership, FamilyBranch, Household, HouseholdMembership, Place
from app.modules.family import service
from app.modules.family.schemas import (
    BranchDetailOut,
    BranchIn,
    BranchMemberOut,
    BranchMembersIn,
    BranchOut,
    BranchUpdate,
    DeriveOut,
    HouseholdDetailOut,
    HouseholdIn,
    HouseholdMemberIn,
    HouseholdMemberOut,
    HouseholdOut,
    HouseholdUpdate,
    PersonHouseholdOut,
)
from app.modules.genealogy import lookup
from app.modules.genealogy.serialize import Serializer

router = APIRouter(prefix="/trees/{tree_id}", tags=["family"])


def _branch_out(ctx, b: FamilyBranch) -> BranchOut:  # type: ignore[no-untyped-def]
    n = (
        ctx.db.scalar(
            select(func.count())
            .select_from(BranchMembership)
            .where(BranchMembership.tree_id == ctx.tree_id, BranchMembership.branch_id == b.id)
        )
        or 0
    )
    return BranchOut.model_validate(b).model_copy(update={"member_count": int(n)})


@router.get("/branches", response_model=list[BranchOut])
def list_branches(ctx: TreeCtx) -> list[BranchOut]:
    rows = ctx.db.scalars(
        select(FamilyBranch).where(FamilyBranch.tree_id == ctx.tree_id).order_by(FamilyBranch.name)
    )
    return [_branch_out(ctx, b) for b in rows]


@router.post("/branches", response_model=BranchOut, status_code=status.HTTP_201_CREATED)
def create_branch(body: BranchIn, ctx: TreeCtx) -> BranchOut:
    return _branch_out(ctx, service.create_branch(ctx, body))


@router.get("/branches/{branch_id}", response_model=BranchDetailOut)
def get_branch(branch_id: uuid.UUID, ctx: TreeCtx) -> BranchDetailOut:
    b = service.get_branch(ctx, branch_id)
    rows = ctx.db.execute(
        select(BranchMembership.person_id, BranchMembership.basis).where(
            BranchMembership.tree_id == ctx.tree_id, BranchMembership.branch_id == b.id
        )
    ).all()
    subjects = lookup.visible_subjects(ctx, [r[0] for r in rows])
    summaries = Serializer(ctx).summaries(subjects)
    members = [BranchMemberOut(person=summaries[pid], basis=basis) for pid, basis in rows if pid in summaries]
    members.sort(key=lambda m: (m.basis != "founder", m.person.display_name if m.person else ""))
    base = _branch_out(ctx, b)
    return BranchDetailOut(**base.model_dump(), members=members, hidden_member_count=len(rows) - len(members))


@router.patch("/branches/{branch_id}", response_model=BranchOut)
def update_branch(branch_id: uuid.UUID, body: BranchUpdate, ctx: TreeCtx) -> BranchOut:
    return _branch_out(ctx, service.update_branch(ctx, branch_id, body))


@router.delete("/branches/{branch_id}", response_model=Message)
def delete_branch(branch_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_branch(ctx, branch_id)
    return Message(message="Branch deleted")


@router.post("/branches/{branch_id}/members", response_model=DeriveOut)
def add_branch_members(branch_id: uuid.UUID, body: BranchMembersIn, ctx: TreeCtx) -> DeriveOut:
    added = service.add_branch_members(ctx, branch_id, body.person_ids)
    return DeriveOut(added=added, total=_branch_out(ctx, service.get_branch(ctx, branch_id)).member_count)


@router.delete("/branches/{branch_id}/members/{person_id}", response_model=Message)
def remove_branch_member(branch_id: uuid.UUID, person_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.remove_branch_member(ctx, branch_id, person_id)
    return Message(message="Removed from branch")


@router.post("/branches/{branch_id}/derive-members", response_model=DeriveOut)
def derive_members(branch_id: uuid.UUID, ctx: TreeCtx) -> DeriveOut:
    added, total = service.derive_members(ctx, branch_id)
    return DeriveOut(added=added, total=total)


# ------------------------------------------------------------------ households
def _household_out(ctx, h: Household) -> HouseholdOut:  # type: ignore[no-untyped-def]
    n = (
        ctx.db.scalar(
            select(func.count())
            .select_from(HouseholdMembership)
            .where(HouseholdMembership.tree_id == ctx.tree_id, HouseholdMembership.household_id == h.id)
        )
        or 0
    )
    place = (
        ctx.db.scalar(
            select(Place.canonical_name).where(Place.tree_id == ctx.tree_id, Place.id == h.place_id)
        )
        if h.place_id
        else None
    )
    return HouseholdOut.model_validate(h).model_copy(update={"member_count": int(n), "place_name": place})


@router.get("/households", response_model=list[HouseholdOut])
def list_households(ctx: TreeCtx, branch_id: uuid.UUID | None = None) -> list[HouseholdOut]:
    q = select(Household).where(Household.tree_id == ctx.tree_id)
    if branch_id:
        q = q.where(Household.branch_id == branch_id)
    return [_household_out(ctx, h) for h in ctx.db.scalars(q.order_by(Household.name))]


@router.post("/households", response_model=HouseholdOut, status_code=status.HTTP_201_CREATED)
def create_household(body: HouseholdIn, ctx: TreeCtx) -> HouseholdOut:
    return _household_out(ctx, service.create_household(ctx, body))


@router.get("/households/{household_id}", response_model=HouseholdDetailOut)
def get_household(household_id: uuid.UUID, ctx: TreeCtx) -> HouseholdDetailOut:
    h = service.get_household(ctx, household_id)
    ms = list(
        ctx.db.scalars(
            select(HouseholdMembership).where(
                HouseholdMembership.tree_id == ctx.tree_id, HouseholdMembership.household_id == h.id
            )
        )
    )
    subjects = lookup.visible_subjects(ctx, [m.person_id for m in ms])
    summaries = Serializer(ctx).summaries(subjects)
    members = [
        HouseholdMemberOut(
            id=m.id,
            person=summaries[m.person_id],
            role=m.role,
            start_date=m.start_date,
            end_date=m.end_date,
            current=m.end_date is None,
        )
        for m in ms
        if m.person_id in summaries
    ]
    order = ["karta", "head", "reference_person", "member", "dependent", "other"]
    members.sort(
        key=lambda m: (not m.current, order.index(m.role.value), m.person.display_name if m.person else "")
    )
    return HouseholdDetailOut(
        **_household_out(ctx, h).model_dump(), members=members, hidden_member_count=len(ms) - len(members)
    )


@router.patch("/households/{household_id}", response_model=HouseholdOut)
def update_household(household_id: uuid.UUID, body: HouseholdUpdate, ctx: TreeCtx) -> HouseholdOut:
    return _household_out(ctx, service.update_household(ctx, household_id, body))


@router.delete("/households/{household_id}", response_model=Message)
def delete_household(household_id: uuid.UUID, ctx: TreeCtx) -> Message:
    service.delete_household(ctx, household_id)
    return Message(message="Household deleted")


@router.post(
    "/households/{household_id}/members",
    response_model=HouseholdMemberOut,
    status_code=status.HTTP_201_CREATED,
)
def add_household_member(
    household_id: uuid.UUID, body: HouseholdMemberIn, ctx: TreeCtx
) -> HouseholdMemberOut:
    m = service.add_household_member(ctx, household_id, body)
    subj = lookup.get_person_subject(ctx, m.person_id)
    summary = Serializer(ctx).summaries({subj.id: subj})[subj.id]
    return HouseholdMemberOut(
        id=m.id,
        person=summary,
        role=m.role,
        start_date=m.start_date,
        end_date=m.end_date,
        current=m.end_date is None,
    )


class EndMembershipIn(ApiModel):
    end_date: GenealogicalDate | None = None
    delete: bool = False


@router.post("/households/{household_id}/members/{membership_id}/end", response_model=Message)
def end_household_member(
    household_id: uuid.UUID, membership_id: uuid.UUID, body: EndMembershipIn, ctx: TreeCtx
) -> Message:
    service.end_household_member(ctx, household_id, membership_id, body.end_date, body.delete)
    return Message(message="Membership updated")


@router.get("/people/{person_id}/households", response_model=list[PersonHouseholdOut])
def person_households(person_id: uuid.UUID, ctx: TreeCtx) -> list[PersonHouseholdOut]:
    lookup.get_person(ctx, person_id)
    rows = ctx.db.execute(
        select(HouseholdMembership, Household)
        .join(
            Household,
            (Household.id == HouseholdMembership.household_id)
            & (Household.tree_id == HouseholdMembership.tree_id),
        )
        .where(HouseholdMembership.tree_id == ctx.tree_id, HouseholdMembership.person_id == person_id)
    ).all()
    return [
        PersonHouseholdOut(
            household=_household_out(ctx, h), role=m.role, start_date=m.start_date, end_date=m.end_date
        )
        for m, h in rows
    ]
