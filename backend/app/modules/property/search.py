"""Property search provider: property names and parcel identifiers (khasra, survey, ULPIN, …).

Registered with ``app.modules.search.providers``; applies property authorisation itself.
"""

from __future__ import annotations

from sqlalchemy import or_, select

from app.authz.context import TreeContext
from app.models import LandParcel, Property
from app.modules.property import service
from app.modules.search import providers
from app.modules.search.schemas import SearchHit

_IDENTIFIER_LABELS = (
    ("khasra_or_gata_number", "khasra/gata number"),
    ("survey_number", "survey number"),
    ("ulpin", "ULPIN"),
    ("khata_number", "khata number"),
    ("khatauni_number", "khatauni number"),
    ("patta_number", "patta number"),
    ("plot_number", "plot number"),
    ("subdivision_number", "subdivision number"),
)


def _escape(q: str) -> str:
    return q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_properties(ctx: TreeContext, q: str, limit: int) -> list[SearchHit]:
    if ctx.public or not ctx.is_member:
        return []
    q = q.strip()
    if not q:
        return []
    like = f"%{_escape(q)}%"
    hits: dict[str, SearchHit] = {}
    for p in ctx.db.scalars(
        select(Property)
        .where(Property.tree_id == ctx.tree_id, Property.display_name.ilike(like, escape="\\"))
        .limit(limit * 3)
    ):
        if not service.can_view_property(ctx, p):
            continue
        exact = p.display_name.casefold() == q.casefold()
        hits[str(p.id)] = SearchHit(
            kind="property",
            id=p.id,
            title=p.display_name,
            subtitle=p.property_type.value.replace("_", " "),
            score=0.85 if exact else 0.7,
            match_tier="exact" if exact else "contains",
            match_reason=f'property name contains "{q}"',
        )
    cols = [getattr(LandParcel, c) for c, _ in _IDENTIFIER_LABELS]
    rows = ctx.db.execute(
        select(LandParcel, Property)
        .join(Property, (Property.id == LandParcel.property_id) & (Property.tree_id == LandParcel.tree_id))
        .where(LandParcel.tree_id == ctx.tree_id, or_(*[c.ilike(like, escape="\\") for c in cols]))
        .limit(limit * 3)
    ).all()
    for parcel, p in rows:
        if str(p.id) in hits or not service.can_view_property(ctx, p):
            continue
        label, value = next(
            (
                (lbl, getattr(parcel, c))
                for c, lbl in _IDENTIFIER_LABELS
                if getattr(parcel, c) and q.casefold() in getattr(parcel, c).casefold()
            ),
            ("identifier", q),
        )
        exact = str(value).casefold() == q.casefold()
        where = ", ".join(x for x in (parcel.village, parcel.district) if x)
        hits[str(p.id)] = SearchHit(
            kind="property",
            id=p.id,
            title=p.display_name,
            subtitle=f"{label} {value}" + (f" · {where}" if where else ""),
            score=0.9 if exact else 0.72,
            match_tier="exact" if exact else "contains",
            match_reason=f'parcel {label} {"is" if exact else "contains"} "{q}"',
        )
    return sorted(hits.values(), key=lambda h: -h.score)[:limit]


def register() -> None:
    providers.register("property", search_properties)
