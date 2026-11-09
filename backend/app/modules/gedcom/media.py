"""Photos imported with a GEDCOM package (ADR-0013).

Upload: each person's staged ``FILE`` references are matched to package members (names only).
Commit: each matched photo of a newly created person goes through the ordinary document upload
pipeline (type allowlist → malware scan → encrypted write-once storage → person link → previews).
"""

from __future__ import annotations

import uuid
from collections import Counter
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.authz.privacy import _RANK
from app.core.config import get_settings
from app.core.errors import Conflict, Unprocessable
from app.core.filetypes import sniff
from app.core.storage import get_store
from app.models import Document, ImportJob, Person
from app.models.enums import DocumentCategory, DocumentLinkTarget, PrivacyLevel, RecordPrivacyLevel
from app.modules.documents import service as documents
from app.modules.documents.schemas import DocumentLinkIn
from app.modules.gedcom import package

if TYPE_CHECKING:
    from app.modules.gedcom.importer import Importer

MAX_LISTED = 20  # names of missing/ambiguous files shown in the report


def _files(staged: dict[str, Any]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    return [
        (ind, f) for ind in staged.get("individuals", []) for m in ind.get("media") or [] for f in m["files"]
    ]


def match(staged: dict[str, Any], pkg: package.Package | None) -> dict[str, Any]:
    """Annotate staged photo references with their package member; return the report section."""
    outcomes: Counter[str] = Counter()
    missing: list[str] = []
    ambiguous: list[str] = []
    people: set[str] = set()
    for ind, f in _files(staged):
        if pkg is None:
            f["outcome"] = "not_in_upload"
            outcomes["not_in_upload"] += 1
            continue
        member, outcome = pkg.match(f["file"])
        f["member"] = member
        f["outcome"] = outcome
        outcomes[outcome] += 1
        if outcome == "matched":
            people.add(ind["xref"])
        elif outcome == "missing" and len(missing) < MAX_LISTED:
            missing.append(package.basename(f["file"]))
        elif outcome == "ambiguous" and len(ambiguous) < MAX_LISTED:
            ambiguous.append(package.basename(f["file"]))
    return {
        "package": pkg is not None,
        "referenced": sum(outcomes.values()),
        "matched": outcomes["matched"],
        "missing": outcomes["missing"],
        "ambiguous": outcomes["ambiguous"],
        "people_with_photos": len(people),
        "missing_files": missing,
        "ambiguous_files": ambiguous,
        "ignored_entries": pkg.ignored if pkg else 0,
    }


def _stricter(a: PrivacyLevel, b: PrivacyLevel) -> PrivacyLevel:
    """The more private of two levels (CUSTOM, which has no rank, keeps the current level)."""
    if a in _RANK and b in _RANK:
        return a if _RANK[a] >= _RANK[b] else b
    return a


def import_photos(ctx: TreeContext, job: ImportJob, imp: Importer) -> dict[str, Any]:
    """Store and link the matched photos of newly created people. Returns counts, warnings, new ids."""
    counts: Counter[str] = Counter()
    warnings: list[dict[str, Any]] = []
    wanted = [(ind, f) for ind, f in _files(job.staged or {}) if f.get("member")]
    result: dict[str, Any] = {"counts": counts, "warnings": warnings, "new_document_ids": []}
    if not wanted or not job.original_storage_key:
        return result
    if not ctx.has(Permission.DOCUMENT_UPLOAD):
        counts["photos_skipped"] += len(wanted)
        warnings.append(
            {
                "code": "photos_need_upload_permission",
                "message": "Photos were not imported: you cannot upload documents",
            }
        )
        return result
    settings = get_settings()
    pkg = package.open_package(
        get_store().get(job.original_storage_key), max_total_bytes=settings.max_gedcom_package_bytes
    )
    stored: dict[str, Document | None] = {}  # member → document (None: rejected)
    created_here: set[uuid.UUID] = set()
    for ind, f in wanted:
        xref = ind["xref"]
        if xref not in imp.created:
            counts["photos_skipped_attached"] += 1
            continue
        person = ctx.db.scalar(
            select(Person).where(Person.tree_id == ctx.tree_id, Person.id == imp.person_map[xref])
        )
        if person is None:
            continue
        member = f["member"]
        name = package.basename(pkg.members[member].filename)  # original case, for title and filename
        link = DocumentLinkIn(
            target_type=DocumentLinkTarget.PERSON, target_id=person.id, note="Imported with the GEDCOM file"
        )
        if member not in stored:
            try:
                content = pkg.read(member, settings.max_upload_bytes)
                kind = sniff(content)
                # photos are filed as photos; a scanned PDF or a recording referenced the same way as "other"
                is_image = kind is not None and kind.mime.startswith("image/")
                doc = documents.upload(
                    ctx,
                    data=content,
                    filename=name,
                    category=DocumentCategory.PHOTO if is_image else DocumentCategory.OTHER,
                    title=(f.get("title") or name)[:300],
                    privacy_level=person.privacy_level,
                    link=link,
                )
            except Conflict as exc:
                if exc.code != "duplicate_document":
                    raise
                # already in the tree and visible to the importer: link it instead of storing it again
                existing_id = (exc.details or {}).get("existing_document_id")
                stored[member] = ctx.db.scalar(
                    select(Document).where(Document.tree_id == ctx.tree_id, Document.id == existing_id)
                )
            except Unprocessable as exc:  # not an allowed image, flagged by the scanner, too large
                stored[member] = None
                counts["photos_rejected"] += 1
                warnings.append({"code": "photo_rejected", "message": f"{name}: {exc.message}"})
                continue
            else:
                stored[member] = doc
                created_here.add(doc.id)
                result["new_document_ids"].append(str(doc.id))
                counts["photos_imported"] += 1
                continue
        linked = stored[member]
        if linked is None:
            continue
        if linked.id in created_here:
            # one photo, several people: never less private than the most private of them
            if linked.privacy_level in PrivacyLevel.__members__.values():  # not ONLY_ME/SELECTED_MEMBERS
                linked.privacy_level = RecordPrivacyLevel(
                    _stricter(PrivacyLevel(linked.privacy_level), person.privacy_level)
                )
        try:
            documents._add_link(ctx, linked, link)
            counts["photos_linked"] += 1
        except Conflict:
            pass  # already linked to this person
    return result
