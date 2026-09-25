"""GEDCOM import jobs and export (PRS §22; ADR-0008)."""

from __future__ import annotations

import datetime as dt
import hashlib
import logging
import uuid
from collections import defaultdict
from typing import Any

import jellyfish
from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.core import audit
from app.core.config import get_settings
from app.core.dates import GenealogicalDate
from app.core.errors import ApiError, Conflict, NotFound, Unprocessable
from app.core.ids import uuid7
from app.core.storage import get_store
from app.core.textnorm import search_key
from app.models import ExportJob, ImportJob, NameRecord
from app.models.enums import JobStatus
from app.modules.gedcom import importer, mapping, parser
from app.modules.gedcom.exporter import Exporter
from app.modules.gedcom.schemas import (
    CommitIn,
    DuplicateMatch,
    ImportJobOut,
    ImportJobSummary,
    StagedPersonPreview,
)
from app.modules.genealogy import lookup
from app.modules.genealogy.serialize import Serializer

log = logging.getLogger(__name__)

MAX_RECORDS = 250_000
MAX_DUPLICATE_CHECK = 5_000
DUPLICATE_MIN_SCORE = 0.55
NAME_SIMILARITY_MIN = 0.82


# --------------------------------------------------------------------------- duplicates
def find_duplicates(ctx: TreeContext, individuals: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Existing people who may be the same as staged individuals (name similarity + birth year).

    Same scoring as app.modules.search.duplicates: Jaro-Winkler over normalised names, ±1 year birth
    bonus, >5 year penalty, sex mismatch penalty. Only people visible to the uploader are considered.
    """
    names: dict[uuid.UUID, set[str]] = defaultdict(set)
    for pid, text in ctx.db.execute(
        select(NameRecord.person_id, NameRecord.search_text).where(NameRecord.tree_id == ctx.tree_id)
    ):
        if text:
            names[pid].add(text)
    if not names:
        return {}
    subjects = lookup.visible_subjects(ctx, names.keys())
    blocks: dict[str, set[uuid.UUID]] = defaultdict(set)
    for pid in subjects:
        for n in names[pid]:
            for tok in n.split():
                blocks[tok[:2]].add(pid)
    out: dict[str, list[dict[str, Any]]] = {}
    for ind in individuals[:MAX_DUPLICATE_CHECK]:
        keys = {
            search_key(n.get("given"), n.get("surname")) or search_key(n.get("full"))
            for n in ind.get("names", [])
        } - {""}
        if not keys:
            continue
        cands: set[uuid.UUID] = set()
        for k in keys:
            for tok in k.split():
                cands |= blocks.get(tok[:2], set())
        byear = next(
            (
                (e.get("date") or {}).get("year")
                for e in ind.get("events", [])
                if e.get("type") == "birth" and (e.get("date") or {}).get("year")
            ),
            None,
        )
        found: list[dict[str, Any]] = []
        for pid in cands:
            best, why = 0.0, None
            for x in keys:
                for y in names[pid]:
                    sim = jellyfish.jaro_winkler_similarity(x, y)
                    if sim > best:
                        best, why = sim, f'names "{x}" / "{y}" similarity {sim:.2f}'
            if best < NAME_SIMILARITY_MIN:
                continue
            reasons = [why] if why else []
            score = 0.5 * best
            s = subjects[pid]
            ey = s.birth_date.year if s.birth_date else None
            if byear and ey:
                if abs(byear - ey) <= 1:
                    score += 0.25
                    reasons.append(f"birth years {byear} / {ey}")
                elif abs(byear - ey) > 5:
                    score -= 0.3
            sex = ind.get("sex")
            if (
                sex
                and sex != "unknown"
                and s.person.sex_at_birth
                and s.person.sex_at_birth.value != "unknown"
            ):
                if s.person.sex_at_birth.value != sex:
                    score -= 0.4
                else:
                    score += 0.05
                    reasons.append("same recorded sex")
            if score >= DUPLICATE_MIN_SCORE:
                found.append(
                    {
                        "person_id": str(pid),
                        "score": round(min(score, 1.0), 3),
                        "outcome": "probable" if score >= 0.8 else "possible",
                        "reasons": reasons,
                    }
                )
        if found:
            found.sort(key=lambda d: -d["score"])
            out[ind["xref"]] = found[:5]
    return out


# --------------------------------------------------------------------------- jobs
def _counts(job: ImportJob) -> dict[str, int]:
    return dict((job.report or {}).get("counts") or {})


def summary(job: ImportJob) -> ImportJobSummary:
    return ImportJobSummary(
        id=job.id,
        status=job.status,
        original_filename=job.original_filename,
        detected_version=job.detected_version,
        detected_encoding=job.detected_encoding,
        counts=_counts(job),
        error=job.error,
        created_at=job.created_at,
        committed_at=job.committed_at,
    )


def get_job(ctx: TreeContext, job_id: uuid.UUID, *, lock: bool = False) -> ImportJob:
    ctx.require(Permission.GEDCOM_IMPORT)
    q = select(ImportJob).where(ImportJob.tree_id == ctx.tree_id, ImportJob.id == job_id)
    if lock:
        q = q.with_for_update()
    job = ctx.db.scalar(q)
    if job is None:
        raise NotFound("Import not found")
    return job


def list_jobs(ctx: TreeContext) -> list[ImportJobSummary]:
    ctx.require(Permission.GEDCOM_IMPORT)
    jobs = ctx.db.scalars(
        select(ImportJob)
        .where(ImportJob.tree_id == ctx.tree_id)
        .order_by(ImportJob.created_at.desc(), ImportJob.id.desc())
        .limit(100)
    )
    return [summary(j) for j in jobs]


def upload(ctx: TreeContext, filename: str | None, data: bytes) -> ImportJob:
    ctx.require(Permission.GEDCOM_IMPORT)
    settings = get_settings()
    if len(data) > settings.max_upload_bytes:
        raise ApiError(
            "The file is larger than the upload limit",
            code="file_too_large",
            status_code=413,
            details={"max_bytes": settings.max_upload_bytes},
        )
    if not data.strip():
        raise Unprocessable("The file is empty", code="empty_file")
    if data[:4] == b"PK\x03\x04":
        raise Unprocessable(
            "GEDZIP (.gdz) packages are not supported yet; upload the .ged file", code="unsupported_format"
        )
    if not parser.looks_like_gedcom(data):
        raise Unprocessable("This does not look like a GEDCOM file (no '0 HEAD' line)", code="not_gedcom")
    job = ImportJob(
        id=uuid7(),
        tree_id=ctx.tree_id,
        format="gedcom",
        status=JobStatus.RUNNING,
        original_filename=(filename or "upload.ged")[:400],
        created_by=ctx.user_id,
    )
    ctx.db.add(job)
    ctx.db.flush()
    key = f"SYSTEM/{ctx.tree_id}/imports/{job.id}/original.ged"
    get_store().put_immutable(key, data, key_id="STANDARD")
    job.original_storage_key = key
    file_info = {"size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
    try:
        result = parser.parse(data, max_bytes=settings.max_upload_bytes, max_records=MAX_RECORDS)
        staged, report = mapping.stage(result)
        report["duplicates"] = find_duplicates(ctx, staged["individuals"])
        if len(staged["individuals"]) > MAX_DUPLICATE_CHECK:
            report["warnings"].append(
                {
                    "line": None,
                    "code": "duplicates_partial",
                    "message": f"Duplicate check covered the first {MAX_DUPLICATE_CHECK} people only",
                    "severity": "warning",
                }
            )
        report["file"] = file_info
        job.detected_version = (result.version or "unknown")[:20]
        job.detected_encoding = result.encoding[:40]
        job.staged = staged
        job.report = report
        job.status = JobStatus.READY
    except Exception as exc:  # tolerate anything the parser/stager did not anticipate
        log.exception("GEDCOM staging failed for import %s", job.id)
        job.status = JobStatus.FAILED
        job.error = f"The file could not be processed ({type(exc).__name__})"
        job.report = {"file": file_info, "errors": [{"line": None, "code": "internal", "message": job.error}]}
    audit.log(
        ctx,
        "gedcom.uploaded",
        target_type="import_job",
        target_id=job.id,
        details={"status": job.status.value, "version": job.detected_version, "counts": _counts(job)},
    )
    return job


def _preview(
    ctx: TreeContext, job: ImportJob, offset: int, limit: int
) -> tuple[list[StagedPersonPreview], int]:
    individuals = (job.staged or {}).get("individuals", [])
    page = individuals[offset : offset + limit]
    dups: dict[str, list[dict[str, Any]]] = (job.report or {}).get("duplicates") or {}
    ids: set[uuid.UUID] = set()
    for ind in page:
        for d in dups.get(ind["xref"], []):
            ids.add(uuid.UUID(d["person_id"]))
    subjects = lookup.visible_subjects(ctx, ids)
    summaries = Serializer(ctx).summaries(subjects) if subjects else {}

    def vital(ind: dict[str, Any], t: str) -> str | None:
        for e in ind.get("events", []):
            if e.get("type") == t:
                if e.get("date"):
                    return GenealogicalDate.model_validate(e["date"]).display()
                return e.get("date_text") or "yes"
        return None

    out = []
    for ind in page:
        matches = []
        for d in dups.get(ind["xref"], []):
            pid = uuid.UUID(d["person_id"])
            if pid in summaries:  # re-checked against the current viewer
                matches.append(
                    DuplicateMatch(
                        person=summaries[pid], score=d["score"], outcome=d["outcome"], reasons=d["reasons"]
                    )
                )
        out.append(
            StagedPersonPreview(
                xref=ind["xref"],
                display_name=ind.get("display_name") or "Unnamed",
                sex=ind.get("sex"),
                profile_status=ind.get("profile_status") or "unknown",
                birth=vital(ind, "birth"),
                death=vital(ind, "death"),
                names=[mapping._display(n) for n in ind.get("names", [])][:10],
                event_count=len(ind.get("events", [])),
                heritage=sorted({h["attribute"] for h in ind.get("heritage") or []}),
                has_astrology=bool(ind.get("astrology")),
                preserved_tags=sorted({p["tag"] for p in ind.get("preserved") or []}),
                duplicates=matches,
            )
        )
    return out, len(individuals)


def job_out(ctx: TreeContext, job: ImportJob, offset: int = 0, limit: int = 200) -> ImportJobOut:
    report = dict(job.report or {})
    report.pop("duplicates", None)  # returned per person, filtered by visibility
    commit_result = report.pop("commit", None)
    preview, total = _preview(ctx, job, offset, limit)
    return ImportJobOut(
        **summary(job).model_dump(),
        report=report,
        preview=preview,
        preview_total=total,
        commit_result=commit_result,
    )


def commit(ctx: TreeContext, job_id: uuid.UUID, body: CommitIn) -> ImportJob:
    job = get_job(ctx, job_id, lock=True)
    if job.status == JobStatus.COMMITTED:
        raise Conflict("This import has already been committed", code="already_committed")
    if job.status != JobStatus.READY:
        raise Conflict(f"This import cannot be committed (status {job.status.value})", code="not_ready")
    raw = {k: (v if isinstance(v, str) else {"attach": str(v.attach)}) for k, v in body.decisions.items()}
    decisions = importer.normalise_decisions(ctx, job.staged or {}, raw)
    result = importer.Importer(ctx, job, decisions).run()
    job.decisions = {
        x: (kind if pid is None else {"attach": str(pid)}) for x, (kind, pid) in decisions.items()
    }
    job.report = {**(job.report or {}), "commit": result}
    job.status = JobStatus.COMMITTED
    job.committed_at = dt.datetime.now(dt.UTC)
    job.updated_by = ctx.user_id
    audit.log(
        ctx,
        "gedcom.imported",
        target_type="import_job",
        target_id=job.id,
        details={"counts": result["counts"], "warnings": len(result["warnings"])},
    )
    return job


def cancel(ctx: TreeContext, job_id: uuid.UUID) -> ImportJob:
    job = get_job(ctx, job_id, lock=True)
    if job.status == JobStatus.COMMITTED:
        raise Conflict("A committed import cannot be cancelled", code="already_committed")
    if job.status == JobStatus.CANCELLED:
        raise Conflict("This import is already cancelled", code="already_cancelled")
    job.status = JobStatus.CANCELLED
    job.staged = {}  # drop the staged personal data; the original file stays in immutable storage
    job.updated_by = ctx.user_id
    audit.log(ctx, "gedcom.import_cancelled", target_type="import_job", target_id=job.id)
    return job


# --------------------------------------------------------------------------- export
def export(ctx: TreeContext, *, exclude_living: bool, include_sensitive: bool) -> tuple[bytes, str]:
    ctx.require(Permission.GEDCOM_EXPORT)
    if include_sensitive:
        ctx.require(Permission.PRIVACY_MANAGE)
    data, counts = Exporter(ctx, exclude_living=exclude_living, include_sensitive=include_sensitive).run()
    filename = "tree.ged"
    options = {"exclude_living": exclude_living, "include_sensitive": include_sensitive, "version": "7.0"}
    now = dt.datetime.now(dt.UTC)
    job = ExportJob(
        tree_id=ctx.tree_id,
        kind="gedcom",
        options=options,
        status=JobStatus.COMPLETED,
        filename=filename,
        size_bytes=len(data),
        checksum_sha256=hashlib.sha256(data).hexdigest(),
        completed_at=now,
        created_by=ctx.user_id,
    )
    ctx.db.add(job)
    ctx.db.flush()
    audit.log(
        ctx,
        "gedcom.exported",
        target_type="export_job",
        target_id=job.id,
        summary="GEDCOM export including sensitive fields" if include_sensitive else None,
        details={**options, "counts": counts},
    )
    return data, filename
