"""Render payloads (ADR-0017 §payload): built *as the requester* from the visualization APIs.

The renderer only draws what is in the payload. Everything here goes through the same privacy path
as the on-screen charts (visible subjects, redacted dates and places, coordinate privacy, document
content checks for photos), so a video can never show more than the requester could see.
"""

from __future__ import annotations

import base64
import datetime as dt
import uuid
from collections import Counter
from typing import Any

from sqlalchemy import select

from app.authz.context import TreeContext
from app.core.errors import Unprocessable
from app.core.storage import get_store
from app.models import Document, DocumentDerivative, FamilyBranch
from app.models.enums import ChartType, DerivativeKind, ProfileStatus
from app.modules.documents.access import can_access_content
from app.modules.genealogy import engine
from app.modules.genealogy.schemas import PersonSummary
from app.modules.render.schemas import RenderSettings
from app.modules.visualization import service as viz
from app.modules.visualization.schemas import AncestryNode, VizPerson

COMPOSITIONS = {
    ChartType.FAN: "FanChart",
    ChartType.PEDIGREE: "PedigreeChart",
    ChartType.FAMILY_TREE: "FamilyTree",
    ChartType.LIFESPAN: "LifespanTimeline",
    ChartType.EVENT_TIMELINE: "EventTimeline",
}
MAX_TREE_NODES = 60
MAX_LIFESPAN_ROWS = 40
MAX_PHOTOS = 12
MAX_PHOTO_BYTES = 600 * 1024
OTHER = "__other__"


def _years(birth: str | None, death: str | None, status: ProfileStatus) -> str | None:
    if not birth and not death:
        return None
    if status == ProfileStatus.DECEASED:
        return f"{birth or '?'}–{death or '?'}"
    return f"{birth}–" if birth else None


def _card(p: VizPerson | PersonSummary, color_key: str | None = None) -> dict[str, Any]:
    if isinstance(p, VizPerson):
        return {
            "id": str(p.id),
            "name": p.display_name,
            "years": _years(p.birth_display, p.death_display, p.profile_status),
            "birthPlace": p.birth_place.name if p.birth_place else None,
            "village": p.village,
            "living": p.profile_status == ProfileStatus.LIVING,
            "completeness": p.completeness.score if p.completeness else None,
            "colorKey": color_key,
        }
    return {
        "id": str(p.id),
        "name": p.display_name,
        "years": _years(p.birth_display, p.death_display, p.profile_status),
        "living": p.profile_status == ProfileStatus.LIVING,
        "colorKey": color_key,
    }


def _color_key(
    ctx: TreeContext, color_by: str, node: AncestryNode, branches: dict[uuid.UUID, str]
) -> str | None:
    p = node.person
    if p is None:
        return None
    if color_by == "side":
        return node.side
    if color_by == "birthplace":
        return p.birth_place.name if p.birth_place else "unknown"
    if color_by == "village":
        return p.village or "unknown"
    if color_by == "branch":
        return branches.get(p.branch_ids[0], "unknown") if p.branch_ids else "unknown"
    if color_by == "completeness":
        s = p.completeness.score if p.completeness else 0
        return "complete" if s >= 0.8 else "partial" if s >= 0.4 else "sparse"
    return p.profile_status.value


_FIXED_LABELS = {
    "self": "Root person",
    "paternal": "Paternal side",
    "maternal": "Maternal side",
    "complete": "Well documented",
    "partial": "Partly documented",
    "sparse": "Research needed",
    "living": "Living",
    "deceased": "Deceased",
    "unknown": "Unknown",
    OTHER: "Other",
}


def _legend(keys: list[str | None], limit: int = 9) -> tuple[list[dict[str, str]], dict[str, str]]:
    """Most frequent keys get colours; the rest are grouped as "Other"."""
    counts = Counter(k for k in keys if k)
    top = [k for k, _ in counts.most_common(limit)]
    remap = {k: (k if k in top else OTHER) for k in counts}
    entries = [{"key": k, "label": _FIXED_LABELS.get(k, k)} for k in top]
    if any(v == OTHER for v in remap.values()):
        entries.append({"key": OTHER, "label": "Other"})
    return entries, remap


def _branding(
    ctx: TreeContext, s: RenderSettings, default_title: str, default_subtitle: str | None
) -> dict[str, Any]:
    return {
        "title": s.title or default_title,
        "subtitle": s.subtitle if s.subtitle is not None else default_subtitle,
        "treeName": ctx.tree.name,
        "footer": ctx.tree.name,
    }


def _require_root(s: RenderSettings) -> uuid.UUID:
    if s.root_person_id is None:
        raise Unprocessable("Choose a person for this chart", code="root_required")
    return s.root_person_id


def build(ctx: TreeContext, chart: ChartType, s: RenderSettings) -> tuple[str, dict[str, Any]]:
    """Return (composition id, props) for the renderer."""
    if chart not in COMPOSITIONS:
        raise Unprocessable("This chart has no animated export", code="not_animatable")
    data, title, subtitle = _DATA[chart](ctx, s)
    props = {
        "theme": s.theme,
        "branding": _branding(ctx, s, title, subtitle),
        "generatedAt": dt.datetime.now(dt.UTC).isoformat(),
        "music": None,  # narration/music slots: not used until assets exist (ADR-0017)
        "narration": None,
        "data": data,
    }
    return COMPOSITIONS[chart], props


def _slots(ctx: TreeContext, s: RenderSettings, kind: str) -> tuple[dict[str, Any], str, str | None]:
    root = _require_root(s)
    gens = min(s.generations, 6 if kind == "fan" else 5)
    a = viz.ancestry(ctx, root, gens, set(s.lineage) if s.lineage else None)
    branches = (
        {
            b.id: b.name
            for b in ctx.db.scalars(select(FamilyBranch).where(FamilyBranch.tree_id == ctx.tree_id))
        }
        if s.color_by == "branch"
        else {}
    )
    raw = {n.slot: _color_key(ctx, s.color_by, n, branches) for n in a.nodes}
    legend, remap = _legend(list(raw.values()))
    nodes = [
        {
            "slot": n.slot,
            "generation": n.generation,
            "hidden": n.hidden,
            "person": _card(n.person, remap.get(raw[n.slot] or "", None)) if n.person else None,
        }
        for n in a.nodes
    ]
    root_name = next((n.person.display_name for n in a.nodes if n.slot == 1 and n.person), "")
    data = {
        "kind": kind,
        "generations": gens,
        "colorBy": s.color_by,
        "nodes": nodes,
        "legend": legend,
        "missingSlots": a.missing_slots,
    }
    return data, f"Ancestors of {root_name}", f"{gens} generations"


def _fan(ctx: TreeContext, s: RenderSettings) -> tuple[dict[str, Any], str, str | None]:
    return _slots(ctx, s, "fan")


def _pedigree(ctx: TreeContext, s: RenderSettings) -> tuple[dict[str, Any], str, str | None]:
    return _slots(ctx, s, "pedigree")


def _family_tree(ctx: TreeContext, s: RenderSettings) -> tuple[dict[str, Any], str, str | None]:
    root = _require_root(s)
    g = engine.graph(
        ctx,
        root,
        s.direction,
        min(s.generations, 6),
        set(s.lineage) if s.lineage else None,
        max_nodes=MAX_TREE_NODES,
    )
    nodes = [
        {
            "id": n.id,
            "generation": n.generation,
            "hidden": n.hidden,
            "partner": n.partner,
            "person": _card(n.person) if n.person else None,
        }
        for n in g.nodes[:MAX_TREE_NODES]
    ]
    keep = {n["id"] for n in nodes}
    root_name = next((n.person.display_name for n in g.nodes if n.id == str(root) and n.person), "")
    data = {
        "kind": "family_tree",
        "direction": s.direction,
        "rootId": str(root),
        "nodes": nodes,
        "edges": [
            {"source": e.source, "target": e.target} for e in g.edges if e.source in keep and e.target in keep
        ],
        "unions": [{"a": u["a"], "b": u["b"]} for u in g.unions if u["a"] in keep and u["b"] in keep],
    }
    word = "Descendants" if s.direction == "descendants" else "Ancestors"
    return data, f"{word} of {root_name}", None


def _lifespan(ctx: TreeContext, s: RenderSettings) -> tuple[dict[str, Any], str, str | None]:
    ls = viz.lifespans(ctx, s.root_person_id, s.generations, s.branch_id, True, MAX_LIFESPAN_ROWS)
    rows = [
        {
            "name": r.person.display_name,
            "start": r.start_year,
            "end": r.end_year,
            "endKnown": r.end_known,
            "living": r.person.profile_status == ProfileStatus.LIVING,
            "colorKey": "living" if r.person.profile_status == ProfileStatus.LIVING else "deceased",
            "events": [{"year": e.year, "label": e.label} for e in r.events[:6]],
        }
        for r in ls.rows
    ]
    if not rows:
        raise Unprocessable("No lifespans with known birth years to show", code="nothing_to_render")
    data = {
        "kind": "lifespan",
        "rows": rows,
        "minYear": ls.min_year,
        "maxYear": ls.max_year,
        "periods": [{"label": p.label, "startYear": p.start_year, "endYear": p.end_year} for p in ls.periods],
        "legend": [{"key": "deceased", "label": "Deceased"}, {"key": "living", "label": "Living"}],
    }
    return data, "Lifespans across generations", ls.summary


def _photo_uri(ctx: TreeContext, document_id: uuid.UUID) -> str | None:
    doc = ctx.db.scalar(select(Document).where(Document.tree_id == ctx.tree_id, Document.id == document_id))
    if doc is None or doc.deleted_at is not None or not can_access_content(ctx, doc):
        return None
    for kind in (DerivativeKind.PREVIEW, DerivativeKind.THUMBNAIL):
        d = ctx.db.scalar(
            select(DocumentDerivative).where(
                DocumentDerivative.tree_id == ctx.tree_id,
                DocumentDerivative.document_id == doc.id,
                DocumentDerivative.kind == kind,
            )
        )
        if d is not None and d.size_bytes <= MAX_PHOTO_BYTES:
            data = get_store().get(d.storage_key)
            return f"data:{d.mime_type};base64,{base64.b64encode(data).decode()}"
    return None


def _event_timeline(ctx: TreeContext, s: RenderSettings) -> tuple[dict[str, Any], str, str | None]:
    root = _require_root(s)
    st = viz.story(ctx, root)
    budget = MAX_PHOTOS if s.include_photos else 0
    events = []
    for e in st.events[:30]:
        photos = []
        for ph in e.photos[:2]:
            if budget <= 0:
                break
            uri = _photo_uri(ctx, ph.document_id)
            if uri:
                photos.append({"src": uri, "caption": ph.caption})
                budget -= 1
        events.append(
            {
                "label": e.label,
                "dateDisplay": e.date_display,
                "year": e.year,
                "place": e.place.name if e.place else None,
                "description": e.description,
                "relatives": [r["display_name"] for r in e.relatives if r.get("display_name")],
                "photos": photos,
            }
        )
    if not events:
        raise Unprocessable("This person has no life events to show", code="nothing_to_render")
    p = st.person
    data = {
        "kind": "event_timeline",
        "person": {
            "name": p.display_name,
            "years": _years(p.birth_display, p.death_display, p.profile_status),
        },
        "events": events,
    }
    return data, f"The life of {p.display_name}", None


_DATA = {
    ChartType.FAN: _fan,
    ChartType.PEDIGREE: _pedigree,
    ChartType.FAMILY_TREE: _family_tree,
    ChartType.LIFESPAN: _lifespan,
    ChartType.EVENT_TIMELINE: _event_timeline,
}
