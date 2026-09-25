"""Joint-family structures: family branches and households (PRS §15, §16)."""

from __future__ import annotations

import uuid
from collections import deque

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.core import audit
from app.core.dates import DatePrecision, GenealogicalDate, date_to_json
from app.core.errors import Conflict, Unprocessable
from app.models import BranchMembership, FamilyBranch, Household, HouseholdMembership, Person, Relationship
from app.models.enums import DescentRule, EvidenceStatus, RelationshipType, SexAtBirth
from app.modules.family.schemas import BranchIn, BranchUpdate, HouseholdIn, HouseholdMemberIn, HouseholdUpdate
from app.modules.genealogy import lookup

_DESCENT_TYPES = (RelationshipType.BIOLOGICAL_PARENT, RelationshipType.ADOPTIVE_PARENT)


# ------------------------------------------------------------------ branches
def get_branch(ctx: TreeContext, branch_id: uuid.UUID) -> FamilyBranch:
    return lookup.get_in_tree(ctx, FamilyBranch, branch_id, "Branch")


def _check_parent_branch(ctx: TreeContext, branch: FamilyBranch | None, parent_id: uuid.UUID | None) -> None:
    if parent_id is None:
        return
    get_branch(ctx, parent_id)
    cur: uuid.UUID | None = parent_id
    guard = 0
    while cur is not None and guard < 50:
        if branch is not None and cur == branch.id:
            raise Unprocessable("Branch hierarchy would contain a cycle")
        cur = ctx.db.scalar(
            select(FamilyBranch.parent_branch_id).where(
                FamilyBranch.tree_id == ctx.tree_id, FamilyBranch.id == cur
            )
        )
        guard += 1


def create_branch(ctx: TreeContext, body: BranchIn) -> FamilyBranch:
    ctx.require(Permission.FAMILY_WRITE)
    if not ctx.is_admin and ctx.branch_scope is not None:
        # branch-scoped members may only create sub-branches of their own branch
        if body.parent_branch_id != ctx.branch_scope:
            raise Unprocessable("You can only create sub-branches of your own branch")
    if body.founder_person_id:
        lookup.get_person(ctx, body.founder_person_id)
    _check_parent_branch(ctx, None, body.parent_branch_id)
    b = FamilyBranch(tree_id=ctx.tree_id, created_by=ctx.user_id, **body.model_dump())
    ctx.db.add(b)
    ctx.db.flush()
    if body.founder_person_id:
        ctx.db.add(
            BranchMembership(
                tree_id=ctx.tree_id,
                branch_id=b.id,
                person_id=body.founder_person_id,
                basis="founder",
                created_by=ctx.user_id,
            )
        )
    audit.log(ctx, "branch.created", target_type="branch", target_id=b.id)
    return b


def _require_branch_write(ctx: TreeContext, b: FamilyBranch) -> None:
    ctx.require(Permission.FAMILY_WRITE)
    if (
        not ctx.is_admin
        and ctx.branch_scope is not None
        and b.id != ctx.branch_scope
        and b.parent_branch_id != ctx.branch_scope
    ):
        from app.core.errors import Forbidden

        raise Forbidden("You can only manage your own family branch")


def update_branch(ctx: TreeContext, branch_id: uuid.UUID, body: BranchUpdate) -> FamilyBranch:
    b = get_branch(ctx, branch_id)
    _require_branch_write(ctx, b)
    fields = body.model_fields_set
    if "founder_person_id" in fields and body.founder_person_id:
        lookup.get_person(ctx, body.founder_person_id)
    if "parent_branch_id" in fields:
        if body.parent_branch_id == b.id:
            raise Unprocessable("A branch cannot be its own parent")
        _check_parent_branch(ctx, b, body.parent_branch_id)
    for f in fields:
        setattr(b, f, getattr(body, f))
    b.updated_by = ctx.user_id
    audit.log(ctx, "branch.changed", target_type="branch", target_id=b.id, details={"fields": sorted(fields)})
    return b


def delete_branch(ctx: TreeContext, branch_id: uuid.UUID) -> None:
    b = get_branch(ctx, branch_id)
    ctx.require(Permission.TREE_MANAGE)
    ctx.db.execute(
        sa_delete(BranchMembership).where(
            BranchMembership.tree_id == ctx.tree_id, BranchMembership.branch_id == b.id
        )
    )
    ctx.db.delete(b)
    audit.log(ctx, "branch.deleted", target_type="branch", target_id=b.id)


def add_branch_members(
    ctx: TreeContext, branch_id: uuid.UUID, person_ids: list[uuid.UUID], basis: str = "manual"
) -> int:
    b = get_branch(ctx, branch_id)
    _require_branch_write(ctx, b)
    existing = set(
        ctx.db.scalars(
            select(BranchMembership.person_id).where(
                BranchMembership.tree_id == ctx.tree_id, BranchMembership.branch_id == b.id
            )
        )
    )
    added = 0
    for pid in dict.fromkeys(person_ids):
        lookup.get_person(ctx, pid)
        if pid in existing:
            continue
        ctx.db.add(
            BranchMembership(
                tree_id=ctx.tree_id, branch_id=b.id, person_id=pid, basis=basis, created_by=ctx.user_id
            )
        )
        existing.add(pid)
        added += 1
    ctx.db.flush()
    audit.log(
        ctx,
        "branch.members_added",
        target_type="branch",
        target_id=b.id,
        details={"count": added, "basis": basis},
    )
    return added


def remove_branch_member(ctx: TreeContext, branch_id: uuid.UUID, person_id: uuid.UUID) -> None:
    b = get_branch(ctx, branch_id)
    _require_branch_write(ctx, b)
    m = ctx.db.scalar(
        select(BranchMembership).where(
            BranchMembership.tree_id == ctx.tree_id,
            BranchMembership.branch_id == b.id,
            BranchMembership.person_id == person_id,
        )
    )
    if m is None:
        from app.core.errors import NotFound

        raise NotFound("Person is not a member of this branch")
    ctx.db.delete(m)
    audit.log(ctx, "branch.member_removed", target_type="branch", target_id=b.id)


def derive_members(ctx: TreeContext, branch_id: uuid.UUID) -> tuple[int, int]:
    """Add the founder's descendants following the branch's descent rule (PRS §16).

    patrilineal: descent continues only through male members; matrilineal: only through female
    members; bilateral: through everyone. Biological and adoptive (legal) parentage both count.
    """
    b = get_branch(ctx, branch_id)
    _require_branch_write(ctx, b)
    if b.founder_person_id is None:
        raise Unprocessable("Set a founder before deriving branch members", code="founder_required")
    if b.descent_rule == DescentRule.CUSTOM:
        raise Unprocessable("Custom branches are managed manually")
    children: dict[uuid.UUID, list[uuid.UUID]] = {}
    for parent, child in ctx.db.execute(
        select(Relationship.person_a_id, Relationship.person_b_id).where(
            Relationship.tree_id == ctx.tree_id,
            Relationship.type.in_(_DESCENT_TYPES),
            Relationship.evidence_status.notin_([EvidenceStatus.DISPROVEN, EvidenceStatus.SUPERSEDED]),
        )
    ):
        children.setdefault(parent, []).append(child)
    sex = dict(
        ctx.db.execute(select(Person.id, Person.sex_at_birth).where(Person.tree_id == ctx.tree_id)).all()
    )
    carries = {
        DescentRule.PATRILINEAL: lambda p: sex.get(p) == SexAtBirth.MALE,
        DescentRule.MATRILINEAL: lambda p: sex.get(p) == SexAtBirth.FEMALE,
        DescentRule.BILATERAL: lambda p: True,
    }[b.descent_rule]
    found: list[uuid.UUID] = []
    seen = {b.founder_person_id}
    q = deque([b.founder_person_id])
    while q:
        cur = q.popleft()
        if cur != b.founder_person_id and not carries(cur):
            continue
        for c in children.get(cur, []):
            if c not in seen:
                seen.add(c)
                found.append(c)
                q.append(c)
    visible = lookup.visible_subjects(ctx, found)
    added = add_branch_members(ctx, b.id, [p for p in found if p in visible], basis="derived")
    total = int(
        ctx.db.scalar(
            select(func.count())
            .select_from(BranchMembership)
            .where(BranchMembership.tree_id == ctx.tree_id, BranchMembership.branch_id == b.id)
        )
        or 0
    )
    return added, total


# ------------------------------------------------------------------ households
def get_household(ctx: TreeContext, household_id: uuid.UUID) -> Household:
    return lookup.get_in_tree(ctx, Household, household_id, "Household")


def create_household(ctx: TreeContext, body: HouseholdIn) -> Household:
    ctx.require(Permission.FAMILY_WRITE)
    if body.place_id:
        lookup.get_place(ctx, body.place_id)
    if body.branch_id:
        get_branch(ctx, body.branch_id)
    h = Household(
        tree_id=ctx.tree_id,
        created_by=ctx.user_id,
        name=body.name,
        house_name=body.house_name,
        place_id=body.place_id,
        branch_id=body.branch_id,
        start_date=date_to_json(body.start_date),
        end_date=date_to_json(body.end_date),
        notes=body.notes,
    )
    ctx.db.add(h)
    ctx.db.flush()
    audit.log(ctx, "household.created", target_type="household", target_id=h.id)
    return h


def update_household(ctx: TreeContext, household_id: uuid.UUID, body: HouseholdUpdate) -> Household:
    ctx.require(Permission.FAMILY_WRITE)
    h = get_household(ctx, household_id)
    for f in body.model_fields_set:
        v = getattr(body, f)
        if f in ("start_date", "end_date"):
            v = date_to_json(v)
        elif f == "place_id" and v:
            lookup.get_place(ctx, v)
        elif f == "branch_id" and v:
            get_branch(ctx, v)
        setattr(h, f, v)
    h.updated_by = ctx.user_id
    audit.log(ctx, "household.changed", target_type="household", target_id=h.id)
    return h


def delete_household(ctx: TreeContext, household_id: uuid.UUID) -> None:
    ctx.require(Permission.FAMILY_WRITE)
    h = get_household(ctx, household_id)
    ctx.db.execute(
        sa_delete(HouseholdMembership).where(
            HouseholdMembership.tree_id == ctx.tree_id, HouseholdMembership.household_id == h.id
        )
    )
    ctx.db.delete(h)
    audit.log(ctx, "household.deleted", target_type="household", target_id=h.id)


def add_household_member(
    ctx: TreeContext, household_id: uuid.UUID, body: HouseholdMemberIn
) -> HouseholdMembership:
    ctx.require(Permission.FAMILY_WRITE)
    h = get_household(ctx, household_id)
    lookup.get_person(ctx, body.person_id)
    overlapping = ctx.db.scalar(
        select(HouseholdMembership.id).where(
            HouseholdMembership.tree_id == ctx.tree_id,
            HouseholdMembership.household_id == h.id,
            HouseholdMembership.person_id == body.person_id,
            HouseholdMembership.end_date.is_(None),
        )
    )
    if overlapping and body.end_date is None:
        raise Conflict(
            "This person already has an open membership in this household", code="duplicate_membership"
        )
    m = HouseholdMembership(
        tree_id=ctx.tree_id,
        household_id=h.id,
        person_id=body.person_id,
        role=body.role,
        start_date=date_to_json(body.start_date),
        end_date=date_to_json(body.end_date),
        created_by=ctx.user_id,
    )
    ctx.db.add(m)
    ctx.db.flush()
    audit.log(ctx, "household.member_added", target_type="household", target_id=h.id)
    return m


def end_household_member(
    ctx: TreeContext,
    household_id: uuid.UUID,
    membership_id: uuid.UUID,
    end_date: GenealogicalDate | None,
    delete: bool,
) -> None:
    ctx.require(Permission.FAMILY_WRITE)
    h = get_household(ctx, household_id)
    m = lookup.get_in_tree(ctx, HouseholdMembership, membership_id, "Membership")
    if m.household_id != h.id:
        from app.core.errors import NotFound

        raise NotFound("Membership not found")
    lookup.get_person(ctx, m.person_id)
    if delete:
        ctx.db.delete(m)
    else:
        m.end_date = date_to_json(
            end_date or GenealogicalDate(precision=DatePrecision.UNKNOWN)
        )  # never invent a date
    audit.log(
        ctx,
        "household.member_ended" if not delete else "household.member_removed",
        target_type="household",
        target_id=h.id,
    )
