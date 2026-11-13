"""Smart Add Relative (ADR-0020): plan (no writes) → confirmed commit (one transaction) → undo.

The plan is stateless: the client sends the term and the choices made so far, and the server
recomputes everything from the database each time. The commit recomputes the plan with the same
choices and refuses anything that no longer matches, so a stale preview can never write.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import and_, or_, select

from app.authz.assertions import assertion_allows
from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.core import audit
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.models import Assertion, AuditEvent, BranchMembership, Person, Relationship, RelativeAgeOrder
from app.models.enums import (
    PARENT_TYPES,
    UNION_TYPES,
    AssertionSubject,
    HeritageAttribute,
    ProfileStatus,
    RelationshipType,
    SexAtBirth,
)
from app.modules.genealogy import ageorder, engine, lookup, provisional
from app.modules.genealogy import service as genealogy
from app.modules.genealogy.schemas import PersonCreate, PersonSummary, RelatedPerson, RelativeIn
from app.modules.genealogy.serialize import Serializer
from app.modules.heritage import service as heritage
from app.modules.heritage.schemas import AssertionIn
from app.modules.smartadd.schemas import (
    Choice,
    LinkMode,
    SmartAddAncestralVillageOut,
    SmartAddCommitIn,
    SmartAddHopOut,
    SmartAddPlanIn,
    SmartAddPlanOut,
    SmartAddPreviewItem,
    SmartAddStepOut,
    SmartAddTargetOut,
    SmartAddTermOut,
)
from app.modules.smartadd.terms import TERMS, Hop, Term

UNDO_WINDOW = dt.timedelta(minutes=30)
COMMITTED = "smart_add.committed"
UNDONE = "smart_add.undone"


# ------------------------------------------------------------------ catalogue
def list_terms() -> list[SmartAddTermOut]:
    return [
        SmartAddTermOut(
            code=t.code,
            group=t.group,
            hops=[SmartAddHopOut(relation=h.relation, sex=_sex(h.sex), age=h.age) for h in t.hops],
            asks_relative_age=t.target.relation == "sibling" and t.target.age is None and len(t.hops) == 1,
        )
        for t in TERMS.values()
    ]


def _term(code: str) -> Term:
    term = TERMS.get(code)
    if term is None:
        raise Unprocessable(f"Unknown relationship term: {code}", code="unknown_term")
    return term


def _sex(s: str | None) -> SexAtBirth | None:
    return SexAtBirth(s) if s else None


# ------------------------------------------------------------------ candidates
def _matches_sex(p: PersonSummary, hop: Hop) -> bool:
    """Could this recorded relative be the term's mother/brother/…, judging by sex at birth only?"""
    return hop.sex is None or p.sex_at_birth is None or p.sex_at_birth.value == hop.sex


@dataclass
class _Options:
    candidates: list[PersonSummary] = field(default_factory=list)
    hidden: int = 0
    allow_new: bool = True


def _options(ctx: TreeContext, from_id: uuid.UUID, hop: Hop) -> _Options:
    """Existing relatives of ``from_id`` that could be this hop, and whether a new one may be added."""
    fam = engine.family(ctx, from_id)
    related: list[RelatedPerson]
    if hop.relation == "parent":
        related = [r for r in fam.parents if r.relationship_type in PARENT_TYPES]
    elif hop.relation == "sibling":
        related = list(fam.siblings)
    elif hop.relation == "spouse":
        related = [u.partner for u in fam.unions]
    else:
        related = [c for u in fam.unions for c in u.children] + list(fam.other_children)
    seen: set[uuid.UUID] = set()
    out = _Options()
    for r in related:
        if r.person is None:
            out.hidden += 1
            continue
        if r.person.id in seen:
            continue
        seen.add(r.person.id)
        out.candidates.append(r.person)
    # Sex at birth is not the family role a term names (a mother's recorded sex at birth may not be
    # female), so no recorded relative is left out because of it: those whose recorded sex matches
    # the term, or is not recorded, are listed first and the user decides.
    out.candidates.sort(key=lambda p: not _matches_sex(p, hop))
    if hop.relation == "parent":
        # never invite a duplicate parent: not when one is hidden from this user, not when one who
        # could be this parent is already recorded, and not past two biological parents
        bio = sum(1 for r in fam.parents if r.relationship_type == RelationshipType.BIOLOGICAL_PARENT)
        could_be = any(_matches_sex(p, hop) for p in out.candidates)
        out.allow_new = out.hidden == 0 and not could_be and bio < 2
    return out


def _summary(ctx: TreeContext, person_id: uuid.UUID) -> PersonSummary:
    subject = lookup.get_person_subject(ctx, person_id)
    return Serializer(ctx).summaries({subject.id: subject})[subject.id]


# ------------------------------------------------------------------ plan
@dataclass
class _Resolved:
    term: Term
    anchor: PersonSummary
    steps: list[SmartAddStepOut]
    path_ids: list[uuid.UUID | None]  # anchor, then each intermediate (None = new provisional)
    complete: bool


def _ancestral_villages(ctx: TreeContext, anchor_id: uuid.UUID) -> list[SmartAddAncestralVillageOut]:
    branch_ids = set(
        ctx.db.scalars(
            select(BranchMembership.branch_id).where(
                BranchMembership.tree_id == ctx.tree_id,
                BranchMembership.person_id == anchor_id,
            )
        )
    )
    if not branch_ids:
        return []
    assertions = ctx.db.scalars(
        select(Assertion).where(
            Assertion.tree_id == ctx.tree_id,
            Assertion.branch_id.in_(branch_ids),
            Assertion.attribute == HeritageAttribute.ANCESTRAL_VILLAGE.value,
            Assertion.is_preferred.is_(True),
        )
    ).all()
    return [
        SmartAddAncestralVillageOut(
            assertion_id=row.id,
            branch_id=row.branch_id,
            label=row.value_text or "Recorded ancestral village",
            place_id=row.place_id,
        )
        for row in assertions
        if row.branch_id is not None and assertion_allows(ctx, row)
    ]


def _resolve(ctx: TreeContext, anchor_id: uuid.UUID, term: Term, choices: list[Choice]) -> _Resolved:
    ctx.require(Permission.PERSON_WRITE)
    anchor = _summary(ctx, anchor_id)
    if len(choices) > len(term.intermediates):
        raise Unprocessable("More choices than this relationship has steps", code="too_many_choices")
    steps: list[SmartAddStepOut] = []
    path_ids: list[uuid.UUID | None] = [anchor.id]
    current: uuid.UUID | None = anchor.id
    current_summary: PersonSummary | None = anchor
    for i, hop in enumerate(term.intermediates):
        # after a new provisional person there is nothing recorded to choose from
        opts = _Options(allow_new=True) if current is None else _options(ctx, current, hop)
        step = SmartAddStepOut(
            index=i,
            relation=hop.relation,
            sex=_sex(hop.sex),
            age=hop.age,
            from_person=current_summary,
            candidates=opts.candidates,
            hidden_candidates=opts.hidden,
            allow_new=opts.allow_new,
        )
        if i < len(choices):
            choice = choices[i]
            if choice == "new":
                if not opts.allow_new:
                    raise Unprocessable(
                        "A new person cannot be added at this step; choose a recorded relative",
                        code="new_not_allowed",
                    )
                step.chosen = "new"
                current, current_summary = None, None
            else:
                picked = next((c for c in opts.candidates if c.id == choice), None)
                if picked is None:
                    raise Unprocessable(
                        "That person is not a matching relative at this step", code="invalid_choice"
                    )
                step.chosen = picked
                current, current_summary = picked.id, picked
            path_ids.append(current)
        steps.append(step)
    return _Resolved(term, anchor, steps, path_ids, complete=len(choices) == len(term.intermediates))


def _biological_parents(ctx: TreeContext, person_id: uuid.UUID) -> tuple[list[PersonSummary], int]:
    fam = engine.family(ctx, person_id)
    bio = [r for r in fam.parents if r.relationship_type == RelationshipType.BIOLOGICAL_PARENT]
    return [r.person for r in bio if r.person is not None], sum(1 for r in bio if r.person is None)


def _target(ctx: TreeContext, res: _Resolved) -> SmartAddTargetOut:
    hop = res.term.target
    from_id = res.path_ids[-1]
    from_summary = res.anchor if len(res.path_ids) == 1 else _step_person(res.steps[-1])
    link: LinkMode = "explicit_sibling" if hop.relation == "sibling" else hop.relation  # type: ignore[assignment]
    out = SmartAddTargetOut(
        relation=hop.relation, sex=_sex(hop.sex), age=hop.age, from_person=from_summary, link=link
    )
    if from_id is None:
        return out  # attached to a new provisional person: nothing recorded to check
    if hop.relation == "sibling":
        parents, hidden = _biological_parents(ctx, from_id)
        if parents and not hidden:
            out.link = "shared_parents"
            out.shared_parents = parents
    elif hop.relation == "child":
        fam = engine.family(ctx, from_id)
        out.other_parent_options = [u.partner.person for u in fam.unions if u.partner.person is not None]
    elif hop.relation == "parent":
        fam = engine.family(ctx, from_id)
        bio = sum(1 for r in fam.parents if r.relationship_type == RelationshipType.BIOLOGICAL_PARENT)
        if bio >= 2:
            out.blocked = "two_biological_parents"
    return out


def _step_person(step: SmartAddStepOut) -> PersonSummary | None:
    return step.chosen if isinstance(step.chosen, PersonSummary) else None


def plan(ctx: TreeContext, anchor_id: uuid.UUID, body: SmartAddPlanIn) -> SmartAddPlanOut:
    term = _term(body.term)
    res = _resolve(ctx, anchor_id, term, body.choices)
    out = SmartAddPlanOut(
        term=term.code,
        anchor=res.anchor,
        steps=res.steps,
        complete=res.complete,
        ancestral_villages=_ancestral_villages(ctx, anchor_id),
    )
    if not res.complete:
        return out
    target = _target(ctx, res)
    preview = [SmartAddPreviewItem(kind="existing", person=res.anchor)]
    for step in res.steps:
        person = _step_person(step)
        preview.append(
            SmartAddPreviewItem(
                kind="existing" if person else "provisional",
                person=person,
                relation=step.relation,
                link=_link_for(step.relation),
                age=step.age,
            )
        )
    preview.append(
        SmartAddPreviewItem(kind="new", relation=target.relation, link=target.link, age=target.age)
    )
    return out.model_copy(update={"target": target, "preview": preview})


def _link_for(relation: str) -> LinkMode:
    return "explicit_sibling" if relation == "sibling" else relation  # type: ignore[return-value]


# ------------------------------------------------------------------ commit
@dataclass
class _Written:
    people: list[uuid.UUID] = field(default_factory=list)
    relationships: list[uuid.UUID] = field(default_factory=list)
    age_orders: list[uuid.UUID] = field(default_factory=list)
    assertions: list[uuid.UUID] = field(default_factory=list)


def _union_between(ctx: TreeContext, a: uuid.UUID, b: uuid.UUID) -> Relationship | None:
    return ctx.db.scalar(
        select(Relationship).where(
            Relationship.tree_id == ctx.tree_id,
            Relationship.type.in_(list(UNION_TYPES)),
            or_(
                and_(Relationship.person_a_id == a, Relationship.person_b_id == b),
                and_(Relationship.person_a_id == b, Relationship.person_b_id == a),
            ),
        )
    )


def _link(
    ctx: TreeContext,
    from_id: uuid.UUID,
    new_id: uuid.UUID,
    hop: Hop,
    written: _Written,
    other_parent_id: uuid.UUID | None = None,
) -> None:
    """Record the edge(s) that make ``new_id`` the ``hop`` of ``from_id``."""
    if hop.relation == "sibling":
        parents, hidden = _biological_parents(ctx, from_id)
        if parents and not hidden:
            # a real sibling: the new person is a child of the same recorded parents (ADR-0020 §3)
            first = parents[0].id
            second = parents[1].id if len(parents) > 1 else None
            union = _union_between(ctx, first, second) if second else None
            _, rels = genealogy.add_relative(
                ctx,
                first,
                RelativeIn(
                    relation="child",
                    existing_person_id=new_id,
                    union_id=union.id if union else None,
                    other_parent_id=None if union else second,
                ),
            )
        else:
            _, rels = genealogy.add_relative(
                ctx, from_id, RelativeIn(relation="sibling", existing_person_id=new_id)
            )
    elif hop.relation == "child":
        union_id = None
        if other_parent_id is not None:
            union = _union_between(ctx, from_id, other_parent_id)
            if union is None:
                raise Unprocessable(
                    "The other parent must be this person's spouse or partner", code="no_union"
                )
            union_id = union.id
        _, rels = genealogy.add_relative(
            ctx, from_id, RelativeIn(relation="child", existing_person_id=new_id, union_id=union_id)
        )
    else:
        _, rels = genealogy.add_relative(
            ctx, from_id, RelativeIn(relation=hop.relation, existing_person_id=new_id)
        )
    written.relationships.extend(r.id for r in rels)


def _record_age(
    ctx: TreeContext,
    person_id: uuid.UUID,
    other_id: uuid.UUID,
    age: Literal["elder", "younger"],
    written: _Written,
) -> None:
    """``person_id`` is ``age`` than ``other_id``: record it once; refuse a contradiction (409)."""
    row, created = ageorder.record(ctx, person_id, other_id, age)
    if created:
        written.age_orders.append(row.id)


def _record_ancestral_village(
    ctx: TreeContext,
    anchor_id: uuid.UUID,
    person_id: uuid.UUID,
    body: SmartAddCommitIn,
    written: _Written,
) -> None:
    choice = body.ancestral_village
    if choice.choice == "unknown":
        if choice.assertion_id or choice.place_id or (choice.value_text or "").strip():
            raise Unprocessable("Unknown ancestral village cannot carry a value", code="invalid_village")
        return
    source = None
    if choice.choice == "recorded":
        source = next(
            (
                item
                for item in _ancestral_villages(ctx, anchor_id)
                if item.assertion_id == choice.assertion_id
            ),
            None,
        )
        if source is None:
            raise Unprocessable("Choose an authorized recorded ancestral village", code="invalid_village")
        source_row = ctx.db.scalar(
            select(Assertion).where(
                Assertion.tree_id == ctx.tree_id,
                Assertion.id == source.assertion_id,
            )
        )
        if source_row is None or not assertion_allows(ctx, source_row):
            raise Unprocessable("Choose an authorized recorded ancestral village", code="invalid_village")
        value_text = source_row.value_text
        place_id = source_row.place_id
        privacy_level = source_row.privacy_level
    else:
        if choice.assertion_id is not None:
            raise Unprocessable("A new ancestral village cannot name an assertion", code="invalid_village")
        value_text = (choice.value_text or "").strip() or None
        place_id = choice.place_id
        privacy_level = None
        if value_text is None and place_id is None:
            raise Unprocessable("Enter an ancestral village", code="invalid_village")
        if place_id is not None:
            lookup.get_place(ctx, place_id)
    assertion = heritage.create_assertion(
        ctx,
        AssertionSubject.PERSON,
        person_id,
        AssertionIn(
            attribute=HeritageAttribute.ANCESTRAL_VILLAGE,
            value_text=value_text,
            place_id=place_id,
            privacy_level=privacy_level,
            is_preferred=True,
        ),
    )
    written.assertions.append(assertion.id)


def commit(
    ctx: TreeContext, anchor_id: uuid.UUID, body: SmartAddCommitIn
) -> tuple[AuditEvent, Person, _Written]:
    term = _term(body.term)
    res = _resolve(ctx, anchor_id, term, body.choices)
    if not res.complete:
        raise Unprocessable("Choose a person (or 'new') for every step first", code="plan_incomplete")
    target_info = _target(ctx, res)
    if target_info.blocked:
        raise Conflict("This person already has two biological parents", code=target_info.blocked)
    target_hop = term.target
    if body.relative_age is not None and not (target_hop.relation == "sibling" and target_hop.age is None):
        raise Unprocessable(
            "relative_age only applies to a brother or sister", code="relative_age_not_applicable"
        )
    if body.other_parent_id is not None:
        if target_hop.relation != "child":
            raise Unprocessable("other_parent_id only applies to a child", code="other_parent_not_applicable")
        if body.other_parent_id not in {p.id for p in target_info.other_parent_options}:
            raise Unprocessable("The other parent must be this person's spouse or partner", code="no_union")

    written = _Written()
    current: uuid.UUID = res.anchor.id
    if len(body.provisional_sex_at_birth) > len(term.intermediates):
        raise Unprocessable(
            "More provisional entries than this relationship has steps", code="too_many_choices"
        )
    for i, (hop, chosen) in enumerate(zip(term.intermediates, res.path_ids[1:], strict=True)):
        if chosen is None:
            sex = body.provisional_sex_at_birth[i] if i < len(body.provisional_sex_at_birth) else None
            person = genealogy.create_person(
                ctx,
                PersonCreate.model_construct(
                    names=[],
                    profile_status=ProfileStatus.UNKNOWN,
                    sex_at_birth=sex,
                    scripts_used=[],
                    branch_ids=[],
                ),
                provisional=True,
            )
            written.people.append(person.id)
            _link(ctx, current, person.id, hop, written)
            chosen = person.id
        if hop.age is not None:
            _record_age(ctx, chosen, current, hop.age, written)
        current = chosen

    target = genealogy.create_person(ctx, body.new_person)
    written.people.append(target.id)
    _link(ctx, current, target.id, target_hop, written, other_parent_id=body.other_parent_id)
    _record_ancestral_village(ctx, anchor_id, target.id, body, written)
    age = target_hop.age or body.relative_age
    if age is not None and target_hop.relation == "sibling":
        _record_age(ctx, target.id, current, age, written)

    ctx.db.flush()
    event = audit.log(
        ctx,
        COMMITTED,
        target_type="person",
        target_id=target.id,
        details={
            "term": term.code,
            "person_ids": [str(p) for p in written.people],
            "relationship_ids": [str(r) for r in written.relationships],
            "relative_age_order_ids": [str(a) for a in written.age_orders],
            "assertion_ids": [str(a) for a in written.assertions],
        },
    )
    ctx.db.flush()
    return event, target, written


# ------------------------------------------------------------------ undo
def undo(ctx: TreeContext, operation_id: uuid.UUID) -> None:
    ctx.require(Permission.PERSON_WRITE)
    event = ctx.db.scalar(
        select(AuditEvent).where(
            AuditEvent.id == operation_id, AuditEvent.tree_id == ctx.tree_id, AuditEvent.action == COMMITTED
        )
    )
    if event is None:
        raise NotFound("Operation not found")
    if event.actor_user_id != ctx.user_id:
        raise Forbidden("Only the person who added these relatives can undo it")
    if dt.datetime.now(dt.UTC) - event.created_at > UNDO_WINDOW:
        raise Conflict("This can no longer be undone; remove the people individually", code="undo_expired")
    already = ctx.db.scalar(
        select(AuditEvent.id).where(
            AuditEvent.tree_id == ctx.tree_id,
            AuditEvent.action == UNDONE,
            AuditEvent.target_id == event.id,
        )
    )
    if already is not None:
        raise Conflict("Already undone", code="already_undone")

    people = [uuid.UUID(p) for p in event.details.get("person_ids", [])]
    rels = {uuid.UUID(r) for r in event.details.get("relationship_ids", [])}
    ages = [uuid.UUID(a) for a in event.details.get("relative_age_order_ids", [])]
    assertions = [uuid.UUID(a) for a in event.details.get("assertion_ids", [])]
    for pid in people:
        person = ctx.db.scalar(select(Person).where(Person.tree_id == ctx.tree_id, Person.id == pid))
        if person is None or person.deleted_at is not None:
            raise Conflict("Someone has already changed these relatives", code="changed_since")
        others = {r.id for r in genealogy.relationships_of(ctx, pid)} - rels
        if others:
            raise Conflict(
                "These relatives have been connected to other people since; remove them individually",
                code="changed_since",
            )
    for rel_id in rels:
        if ctx.db.scalar(
            select(Relationship.id).where(Relationship.tree_id == ctx.tree_id, Relationship.id == rel_id)
        ):
            genealogy.delete_relationship(ctx, rel_id)
    for age_id in ages:
        row = ctx.db.scalar(
            select(RelativeAgeOrder).where(
                RelativeAgeOrder.tree_id == ctx.tree_id, RelativeAgeOrder.id == age_id
            )
        )
        if row is not None:
            ctx.db.delete(row)
    for assertion_id in assertions:
        heritage.delete_assertion(ctx, assertion_id)
    for pid in people:
        genealogy.delete_person(ctx, pid)
    provisional.revoke_creator_grants(ctx, people)  # after the deletes, which need to see them
    audit.log(ctx, UNDONE, target_type="audit_event", target_id=event.id)
