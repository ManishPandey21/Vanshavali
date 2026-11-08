"""Kinship words for a relationship, the reader's choice of words, and a family's own words
(ADR-0026 §6). Nothing here changes a person: words are chosen from the recorded chain."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.core import audit
from app.core.errors import NotFound
from app.models import BranchMembership, FamilyBranch, KinshipOverride, Person, User
from app.modules.genealogy import lookup
from app.modules.genealogy.schemas import AgeOrderOut
from app.modules.kinship import packs
from app.modules.kinship.resolve import Age, describe, pattern_of, resolve
from app.modules.kinship.schemas import (
    KinshipOverrideIn,
    KinshipOverrideOut,
    KinshipPackOut,
    KinshipTermOut,
)
from app.modules.review import policy as review_policy


def is_reviewer(user: User | None) -> bool:
    """Draft packs are shown to their reviewers only (system administrators)."""
    return bool(user and user.is_system_admin)


def pack_list(user: User) -> list[KinshipPackOut]:
    return [
        KinshipPackOut(
            key=p["key"],
            lang=p["lang"],
            region=p["region"],
            name=p["name"],
            status=p["status"],
            in_use=bool(p.get("in_use")),
            reviewer=p.get("reviewer"),
            reviewed_on=p.get("reviewed_on"),
            source=p["source"],
            licence=p["licence"],
            term_count=len(p["terms"]),
        )
        for p in packs.visible_packs(is_reviewer(user))
    ]


def preference(ctx: TreeContext) -> tuple[str | None, str | None]:
    """The reader's own choice, then the tree's default, then the reader's UI language."""
    user = ctx.user
    if user is not None and user.kinship_lang:
        return user.kinship_lang, user.kinship_region
    if ctx.tree.kinship_lang:
        return ctx.tree.kinship_lang, ctx.tree.kinship_region
    lang = (user.preferred_language if user is not None else "en") or "en"
    return lang.split("-")[0].lower(), None


def set_preference(db: Session, user: User, lang: str | None, region: str | None) -> None:
    user.kinship_lang = lang
    user.kinship_region = region if lang else None
    db.flush()


def _speaker_sex(ctx: TreeContext) -> str | None:
    """Only the viewer's own claimed profile says which form a speaker uses; never guessed."""
    if ctx.user_id is None:
        return None
    sex = ctx.db.scalar(
        select(Person.sex_at_birth).where(
            Person.tree_id == ctx.tree_id, Person.claimed_by_user_id == ctx.user_id
        )
    )
    value = getattr(sex, "value", sex)
    return value if value in ("male", "female") else None


def _override(
    ctx: TreeContext, pattern: str, lang: str, region: str | None, from_id: uuid.UUID, order: str | None
) -> KinshipOverride | None:
    """A family's word for this chain: the from-person's branch first, then the whole tree; an
    age-specific word only when that age order is known."""
    keys = ([f"{pattern}:{order}"] if order in ("elder", "younger") else []) + [pattern]
    rows = list(
        ctx.db.scalars(
            select(KinshipOverride).where(
                KinshipOverride.tree_id == ctx.tree_id,
                KinshipOverride.pattern.in_(keys),
                KinshipOverride.lang == lang,
            )
        )
    )
    rows = [r for r in rows if r.region in (None, region)]
    if not rows:
        return None
    branches = set(
        ctx.db.scalars(
            select(BranchMembership.branch_id).where(
                BranchMembership.tree_id == ctx.tree_id, BranchMembership.person_id == from_id
            )
        )
    )

    def rank(r: KinshipOverride) -> tuple[int, int, int]:
        return (keys.index(r.pattern), 0 if r.branch_id in branches else 1, 0 if r.region == region else 1)

    rows = [r for r in rows if r.branch_id is None or r.branch_id in branches]
    return min(rows, key=rank) if rows else None


def terms_for(
    ctx: TreeContext, from_id: uuid.UUID, chain: Sequence[str], age_orders: Sequence[AgeOrderOut]
) -> list[KinshipTermOut]:
    """The reader's relationship word for a chain, if their language has one; else nothing (the
    English label and description are used)."""
    if not chain:
        return []
    lang, region = preference(ctx)
    pack = packs.choose(lang, region, is_reviewer(ctx.user))
    ages = [Age(a.chain_index, a.order, a.basis) for a in age_orders]
    pattern = pattern_of(chain)
    found = resolve(pack, chain, ages, _speaker_sex(ctx)) if pack else None
    word_lang = pack["lang"] if pack else lang
    if not word_lang or word_lang == "en":
        return []
    own = _override(
        ctx,
        pattern,
        word_lang,
        pack["region"] if pack else region,
        from_id,
        found.age_order if found else None,
    )
    description = describe(pack, chain, ages) if pack else None
    if own is not None:
        return [
            KinshipTermOut(
                pack=pack["key"] if pack else None,
                lang=word_lang,
                region=own.region,
                term=own.word,
                basis=found.basis if found else None,
                review_status="family",
                family_word=True,
                pack_term=found.term if found else None,
                description=description,
            )
        ]
    if found is None or pack is None:
        return []
    return [
        KinshipTermOut(
            pack=pack["key"],
            lang=pack["lang"],
            region=pack["region"],
            term=found.term,
            transliteration=found.transliteration,
            alternatives=found.alternatives,
            basis=found.basis,
            review_status=packs.review_status(pack),  # type: ignore[arg-type]
            description=description,
        )
    ]


# ---------------------------------------------------------------- a family's own words
def _out(r: KinshipOverride) -> KinshipOverrideOut:
    return KinshipOverrideOut.model_validate(r)


def list_overrides(ctx: TreeContext) -> list[KinshipOverrideOut]:
    ctx.require(Permission.TREE_READ)
    rows = ctx.db.scalars(
        select(KinshipOverride)
        .where(KinshipOverride.tree_id == ctx.tree_id)
        .order_by(KinshipOverride.lang, KinshipOverride.pattern)
    )
    return [_out(r) for r in rows]


def put_override(ctx: TreeContext, body: KinshipOverrideIn) -> KinshipOverride:
    """Record (or change) the family's word for a chain, tree-wide or for one branch."""
    ctx.require(Permission.FAMILY_WRITE)
    if body.branch_id is not None:
        lookup.get_in_tree(ctx, FamilyBranch, body.branch_id, "Branch")
    row = ctx.db.scalar(
        select(KinshipOverride).where(
            KinshipOverride.tree_id == ctx.tree_id,
            KinshipOverride.pattern == body.pattern,
            KinshipOverride.lang == body.lang,
            KinshipOverride.branch_id.is_(None)
            if body.branch_id is None
            else KinshipOverride.branch_id == body.branch_id,
        )
    )
    review_policy.require_direct(ctx, "all", [], [row] if row is not None else [])
    if row is None:
        row = KinshipOverride(
            tree_id=ctx.tree_id,
            pattern=body.pattern,
            lang=body.lang,
            branch_id=body.branch_id,
            created_by=ctx.user_id,
        )
        ctx.db.add(row)
    row.word = body.word
    row.region = body.region
    row.updated_by = ctx.user_id
    ctx.db.flush()
    audit.log(
        ctx,
        "kinship.family_word_set",
        target_type="kinship_override",
        target_id=row.id,
        details={"pattern": body.pattern, "lang": body.lang},
    )
    return row


def get_override(ctx: TreeContext, override_id: uuid.UUID) -> KinshipOverride:
    row = ctx.db.get(KinshipOverride, override_id)
    if row is None or row.tree_id != ctx.tree_id:
        raise NotFound("Family word not found")
    return row


def delete_override(ctx: TreeContext, override_id: uuid.UUID) -> None:
    ctx.require(Permission.FAMILY_WRITE)
    row = get_override(ctx, override_id)
    review_policy.require_direct(ctx, "all", [], [row])
    ctx.db.delete(row)
    ctx.db.flush()
    audit.log(
        ctx,
        "kinship.family_word_removed",
        target_type="kinship_override",
        target_id=override_id,
        details={"pattern": row.pattern, "lang": row.lang},
    )
