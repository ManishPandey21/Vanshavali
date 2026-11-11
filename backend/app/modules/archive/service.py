"""Full family-archive export (PRS §43): a ZIP with a manifest, GEDCOM, canonical JSON, property
records, documents and checksums — all generated from the *exporter's* privacy view.

Layout::

    family-export/
      manifest.json
      genealogy/tree.ged
      genealogy/canonical-data.json
      property/properties.json          (only with property.read)
      documents/index.json
      documents/<id>/<filename>          (content the exporter may download; vault only when requested)
      collections/index.json             (photo collections the exporter may see; photos by document id)
      source-index.csv
      checksums.sha256
      README.txt
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import io
import json
import zipfile
from typing import Any

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.core import audit
from app.core.errors import Forbidden
from app.core.storage import get_store
from app.models import (
    Document,
    ExportJob,
    FamilyBranch,
    Household,
    HouseholdMembership,
    Person,
    Place,
    Relationship,
    Source,
)
from app.models.enums import AssertionSubject, JobStatus, StorageClass
from app.modules.documents import access as doc_access
from app.modules.evidence import service as evidence
from app.modules.gedcom import service as gedcom
from app.modules.genealogy import lookup, provisional
from app.modules.genealogy.serialize import Serializer, relationship_out
from app.modules.heritage import service as heritage

ROOT = "family-export"
FORMAT_VERSION = "1.0"


def _json(obj: Any) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2, default=str).encode()


def _safe(name: str) -> str:
    keep = "".join(c if c.isalnum() or c in "._- " else "_" for c in name).strip() or "file"
    return keep[:120]


def build_archive(
    ctx: TreeContext, *, exclude_living: bool, include_sensitive: bool, include_vault_documents: bool
) -> tuple[bytes, str, dict[str, Any]]:
    ctx.require(Permission.GEDCOM_EXPORT)
    if (include_sensitive or include_vault_documents) and not ctx.has(Permission.PRIVACY_MANAGE):
        raise Forbidden("Including sensitive data or vault documents requires tree-admin privacy rights")

    files: dict[str, bytes] = {}
    counts: dict[str, int] = {}

    # --- genealogy: GEDCOM + canonical JSON (both privacy-filtered)
    ged, _ = gedcom.export(ctx, exclude_living=exclude_living, include_sensitive=include_sensitive)
    files["genealogy/tree.ged"] = ged

    persons = ctx.db.scalars(
        select(Person).where(Person.tree_id == ctx.tree_id, Person.deleted_at.is_(None))
    ).all()
    subjects = lookup.visible_subjects(ctx, [p.id for p in persons])
    # same rule as the GEDCOM: unnamed or unverified provisional people are not exported (ADR-0020 §4)
    pending = provisional.pending_ids(ctx)
    counts["excluded_provisional"] = sum(1 for k in subjects if k in pending)  # only ones this user sees
    subjects = {k: v for k, v in subjects.items() if k not in pending}
    if exclude_living:
        subjects = {k: v for k, v in subjects.items() if not v.is_protected}
    ser = Serializer(ctx)
    people_out = []
    events_by_person = ser.events_for(list(subjects), subjects)
    for pid, subj in subjects.items():
        po = ser.person_out(subj).model_dump(mode="json")
        po["events"] = [e.model_dump(mode="json") for e in events_by_person.get(pid, [])]
        po["heritage"] = heritage.profile(ctx, AssertionSubject.PERSON, pid).model_dump(mode="json")
        people_out.append(po)
    visible_ids = set(subjects)
    rels = [
        relationship_out(r).model_dump(mode="json")
        for r in ctx.db.scalars(select(Relationship).where(Relationship.tree_id == ctx.tree_id))
        if r.person_a_id in visible_ids and r.person_b_id in visible_ids
    ]
    places = [
        {
            "id": str(p.id),
            "canonical_name": p.canonical_name,
            "place_type": p.place_type.value,
            "parent_place_id": str(p.parent_place_id) if p.parent_place_id else None,
            "local_names": p.local_names,
            "historical_names": p.historical_names,
        }
        for p in ctx.db.scalars(select(Place).where(Place.tree_id == ctx.tree_id))
    ]
    sources = [
        s
        for s in ctx.db.scalars(select(Source).where(Source.tree_id == ctx.tree_id))
        if evidence.can_view_source(ctx, s)
    ]
    branches = [
        {
            "id": str(b.id),
            "name": b.name,
            "descent_rule": b.descent_rule.value,
            "founder_person_id": str(b.founder_person_id) if b.founder_person_id in visible_ids else None,
            "heritage": heritage.profile(ctx, AssertionSubject.BRANCH, b.id).model_dump(mode="json"),
        }
        for b in ctx.db.scalars(select(FamilyBranch).where(FamilyBranch.tree_id == ctx.tree_id))
    ]
    households = []
    for h in ctx.db.scalars(select(Household).where(Household.tree_id == ctx.tree_id)):
        members = [
            {
                "person_id": str(m.person_id),
                "role": m.role.value,
                "start_date": m.start_date,
                "end_date": m.end_date,
            }
            for m in ctx.db.scalars(
                select(HouseholdMembership).where(
                    HouseholdMembership.tree_id == ctx.tree_id, HouseholdMembership.household_id == h.id
                )
            )
            if m.person_id in visible_ids
        ]
        households.append(
            {
                "id": str(h.id),
                "name": h.name,
                "house_name": h.house_name,
                "start_date": h.start_date,
                "end_date": h.end_date,
                "members": members,
            }
        )
    from app.modules.traditions.service import export_entries

    traditions_out = export_entries(ctx, visible_ids)
    files["genealogy/canonical-data.json"] = _json(
        {
            "format": "vanshavali-canonical",
            "version": FORMAT_VERSION,
            "people": people_out,
            "relationships": rels,
            "places": places,
            "branches": branches,
            "households": households,
            # ADR-0026 §7: entries the exporter may read; GEDCOM has no place for them
            "traditions": traditions_out,
            "sources": [
                {
                    "id": str(s.id),
                    "title": s.title,
                    "source_type": s.source_type.value,
                    "issuing_authority": s.issuing_authority,
                    "repository": s.repository,
                    "record_number": s.record_number if include_sensitive else None,
                    "date": s.date,
                    "url": s.url,
                    "tradition": s.tradition,
                    "document_id": str(s.document_id) if s.document_id else None,
                }
                for s in sources
            ],
        }
    )
    counts.update(
        people=len(people_out),
        relationships=len(rels),
        sources=len(sources),
        places=len(places),
        traditions=len(traditions_out),
    )

    # --- property (only for people allowed to read property records)
    if ctx.has(Permission.PROPERTY_READ):
        from app.modules.property import service as prop_service
        from app.modules.property.serialize import PropertySerializer

        props = prop_service.list_properties(ctx, None, None, None)
        pser = PropertySerializer(ctx)
        files["property/properties.json"] = _json(
            {
                "legal_notice": "Genealogical/documentary record only — not a legal title opinion.",
                "properties": [
                    {
                        "detail": pser.detail(p).model_dump(mode="json"),
                        "timeline": pser.timeline(p).model_dump(mode="json"),
                    }
                    for p in props
                ],
            }
        )
        counts["properties"] = len(props)

    # --- documents: metadata for all visible; bytes only where content access is allowed
    store = get_store()
    doc_index = []
    included = 0
    for d in ctx.db.scalars(
        select(Document).where(Document.tree_id == ctx.tree_id, Document.deleted_at.is_(None))
    ):
        if not doc_access.can_view_document(ctx, d):
            continue
        entry: dict[str, Any] = {
            "id": str(d.id),
            "title": d.title,
            "category": d.category.value,
            "storage_class": d.storage_class.value,
            "original_filename": d.original_filename,
            "mime_type": d.mime_type,
            "sha256": d.checksum_sha256,
            "document_date": d.document_date,
            "included": False,
        }
        wants_bytes = d.storage_class != StorageClass.VAULT or include_vault_documents
        if wants_bytes and doc_access.can_download(ctx, d):  # exports count as downloads (ADR-0027 §4)
            path = f"documents/{d.id}/{_safe(d.original_filename)}"
            files[path] = store.get(d.storage_key)
            entry.update(included=True, path=path)
            included += 1
        doc_index.append(entry)
    files["documents/index.json"] = _json(doc_index)

    # --- photo collections: only those the exporter may see, and in each only their visible photos
    from app.modules.collections.service import export_collections

    collections_out = export_collections(ctx, {e["id"] for e in doc_index})
    files["collections/index.json"] = _json(collections_out)
    counts["collections"] = len(collections_out)
    counts.update(documents_listed=len(doc_index), documents_included=included)

    # --- source index CSV
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["source_id", "title", "type", "issuing_authority", "repository", "document_id"])
    for s in sources:
        w.writerow(
            [
                s.id,
                s.title,
                s.source_type.value,
                s.issuing_authority or "",
                s.repository or "",
                s.document_id or "",
            ]
        )
    files["source-index.csv"] = buf.getvalue().encode()

    # GODL-India attribution for place codes picked from the Local Government Directory (ADR-0019 §9)
    lgd_snapshots = sorted(
        x
        for x in ctx.db.scalars(
            select(Place.lgd_snapshot_id)
            .where(Place.tree_id == ctx.tree_id, Place.lgd_snapshot_id.is_not(None))
            .distinct()
        )
        if x
    )
    lgd_note = (
        "Place codes: Source: Local Government Directory, Government of India; India Post. Used under\n"
        f"the Government Open Data Licence – India (GODL-India). Snapshots: {', '.join(lgd_snapshots)}.\n\n"
        if lgd_snapshots
        else ""
    )
    files["README.txt"] = (
        "Vanshavali family archive\n\n"
        f"Tree: {ctx.tree.name}\nGenerated: {dt.datetime.now(dt.UTC).isoformat()}\n\n"
        "genealogy/tree.ged            GEDCOM 7.0 (Indian extensions documented via HEAD.SCHMA URIs)\n"
        "genealogy/canonical-data.json richer canonical data (names, qualified dates, heritage claims, provenance)\n"
        "property/properties.json      property register, interests and timelines (not a legal title opinion)\n"
        "documents/                    original files you were permitted to export, plus index.json\n"
        "collections/index.json        photo collections you may see; photos are listed by document id\n"
        "checksums.sha256              verify with: sha256sum -c checksums.sha256\n\n"
        + lgd_note
        + "This export reflects what the exporting user was allowed to see. It may contain personal data:\n"
        "store it securely.\n"
    ).encode()

    manifest = {
        "format": "vanshavali-archive",
        "version": FORMAT_VERSION,
        "tree_id": str(ctx.tree_id),
        "tree_name": ctx.tree.name,
        "generated_at": dt.datetime.now(dt.UTC).isoformat(),
        "options": {
            "exclude_living": exclude_living,
            "include_sensitive": include_sensitive,
            "include_vault_documents": include_vault_documents,
        },
        "counts": counts,
        "files": [
            {"path": p, "sha256": hashlib.sha256(b).hexdigest(), "size": len(b)}
            for p, b in sorted(files.items())
        ],
    }
    files["manifest.json"] = _json(manifest)
    checks = "".join(f"{hashlib.sha256(b).hexdigest()}  {p}\n" for p, b in sorted(files.items()))
    files["checksums.sha256"] = checks.encode()

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for path, data in sorted(files.items()):
            z.writestr(f"{ROOT}/{path}", data)
    blob = out.getvalue()
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d")
    filename = f"vanshavali-archive-{stamp}.zip"
    job = ExportJob(
        tree_id=ctx.tree_id,
        kind="archive",
        options=manifest["options"],
        status=JobStatus.COMPLETED,
        filename=filename,
        size_bytes=len(blob),
        checksum_sha256=hashlib.sha256(blob).hexdigest(),
        completed_at=dt.datetime.now(dt.UTC),
        created_by=ctx.user_id,
    )
    ctx.db.add(job)
    ctx.db.flush()
    audit.log(
        ctx,
        "archive.exported",
        target_type="tree",
        target_id=ctx.tree_id,
        details={"options": manifest["options"], "counts": counts, "export_id": str(job.id)},
    )
    return blob, filename, manifest
