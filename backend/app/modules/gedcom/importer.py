"""Commit a staged GEDCOM import into the tree (PRS §22; ADR-0008).

Runs inside the caller's transaction: either everything in the job is written or nothing is.
Decisions per individual are ``create`` (default), ``skip`` or ``attach`` to an existing person.
``attach`` NEVER changes the existing person: it only adds the file's names and events as extra,
non-preferred claims (plus relationships to other imported people). Every created fact carries
``prov_origin=gedcom`` and ``evidence_status=USER_ASSERTION``.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections import Counter
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select

from app.authz.context import TreeContext
from app.authz.permissions import Permission
from app.core.dates import GenealogicalDate
from app.core.errors import NotFound, Unprocessable
from app.models import (
    Assertion,
    Citation,
    Event,
    EventParticipant,
    GedcomExtension,
    ImportJob,
    Person,
    Place,
    Relationship,
    Source,
)
from app.models.enums import (
    DEFAULT_LINEAGE,
    PARENT_TYPES,
    SYMMETRIC_TYPES,
    UNION_TYPES,
    AssertionSubject,
    AstrologyProvenance,
    CitationTarget,
    EventType,
    EvidenceStatus,
    ParticipantRole,
    PrivacyLevel,
    ProfileStatus,
    ProvenanceOrigin,
    RelationshipType,
    SexAtBirth,
    SourceType,
    ValueStatus,
)
from app.modules.astrology import service as astrology_service
from app.modules.astrology.schemas import AstrologyIn
from app.modules.genealogy import lookup
from app.modules.genealogy import service as genealogy
from app.modules.genealogy.schemas import NameIn
from app.modules.genealogy.serialize import name_display

CREATE, SKIP, ATTACH = "create", "skip", "attach"
_POINTER_LINE = re.compile(r"^(\d+) ([A-Za-z0-9_]+) (@[^@]+@)$")
_BIO_EXCLUDED = (EvidenceStatus.DISPROVEN, EvidenceStatus.SUPERSEDED, EvidenceStatus.DISPUTED)


def normalise_decisions(
    ctx: TreeContext, staged: dict[str, Any], raw: dict[str, Any]
) -> dict[str, tuple[str, uuid.UUID | None]]:
    xrefs = [i["xref"] for i in staged.get("individuals", [])]
    known = set(xrefs)
    unknown = sorted(set(raw) - known)
    if unknown:
        raise Unprocessable("Decisions reference unknown individuals", details={"xrefs": unknown[:50]})
    out: dict[str, tuple[str, uuid.UUID | None]] = {}
    attached: dict[uuid.UUID, str] = {}
    for x in xrefs:
        d = raw.get(x, CREATE)
        if d in (CREATE, SKIP):
            out[x] = (d, None)
            continue
        if isinstance(d, dict) and set(d) == {ATTACH}:
            try:
                pid = uuid.UUID(str(d[ATTACH]))
            except ValueError:
                raise Unprocessable(f"Invalid attach target for {x}")
            try:
                person = lookup.get_person(ctx, pid)
            except NotFound:
                raise Unprocessable(f"Attach target for {x} was not found in this tree", code="attach_target")
            ctx.require(Permission.PERSON_WRITE, person_id=person.id)
            if pid in attached:
                raise Unprocessable(
                    f"{x} and {attached[pid]} are both attached to the same person; merge them first",
                    code="attach_conflict",
                )
            attached[pid] = x
            out[x] = (ATTACH, pid)
            continue
        raise Unprocessable(f"Decision for {x} must be 'create', 'skip' or {{'attach': person_id}}")
    return out


def rewrite_pointers(payload: str, person_map: dict[str, uuid.UUID]) -> str:
    """Pointers to imported people become ``@VSH:<uuid>@`` (resolved on export); others ``@VOID@``."""
    lines = []
    for ln in payload.split("\n"):
        m = _POINTER_LINE.match(ln)
        if m and m.group(3) != "@VOID@":
            pid = person_map.get(m.group(3))
            ln = f"{m.group(1)} {m.group(2)} " + (f"@VSH:{pid}@" if pid else "@VOID@")
        lines.append(ln)
    return "\n".join(lines)


class Importer:
    def __init__(self, ctx: TreeContext, job: ImportJob, decisions: dict[str, tuple[str, uuid.UUID | None]]):
        self.ctx = ctx
        self.db = ctx.db
        self.job = job
        self.staged = job.staged or {}
        self.decisions = decisions
        self.now = dt.datetime.now(dt.UTC)
        self.counts: Counter[str] = Counter()
        self.warnings: list[dict[str, Any]] = []
        self.person_map: dict[str, uuid.UUID] = {}
        self.created: set[str] = set()
        self.attached: set[str] = set()
        self.people: dict[uuid.UUID, Person] = {}
        self._places: dict[str, Place] = {}
        self._sources: dict[str, Source] = {}
        self._source_data = {s["xref"]: s for s in self.staged.get("sources", [])}
        self._rel_keys: dict[tuple[str, uuid.UUID, uuid.UUID], Relationship] = {}
        self._union_order: Counter[uuid.UUID] = Counter()
        self._bio_parents: Counter[uuid.UUID] = Counter()
        self._births: dict[uuid.UUID, uuid.UUID] = {}
        self._new_rels: set[uuid.UUID] = set()

    # ------------------------------------------------------------------ helpers
    def prov(self, xref: str | None = None, line: int | None = None) -> dict[str, Any]:
        loc = f"import {self.job.id}"
        if xref:
            loc += f" {xref}"
        if line:
            loc += f" line {line}"
        return {
            "prov_origin": ProvenanceOrigin.GEDCOM,
            "prov_algorithm": "gedcom-import",
            "prov_model_version": (self.staged.get("version") or "unknown")[:80],
            "prov_source_location": loc,
            "prov_extracted_at": self.now,
        }

    def warn(self, code: str, message: str, xref: str | None = None) -> None:
        self.warnings.append({"code": code, "message": message, "xref": xref})

    def place(self, name: str | None) -> Place | None:
        if not name:
            return None
        key = name.strip().lower()
        if key not in self._places:
            self._places[key] = genealogy.find_or_create_place_by_name(self.ctx, name.strip()[:300])
        return self._places[key]

    def source(self, xref: str) -> Source | None:
        if xref in self._sources:
            return self._sources[xref]
        data = self._source_data.get(xref)
        if data is None:
            return None
        notes = "\n\n".join(p for p in (data.get("publication"), data.get("notes")) if p) or None
        s = Source(
            tree_id=self.ctx.tree_id,
            source_type=SourceType.OTHER,
            title=(data.get("title") or "Untitled source")[:400],
            issuing_authority=(data.get("author") or None) and data["author"][:300],
            repository=(data.get("repository") or None) and data["repository"][:300],
            transcription=data.get("text"),
            notes=notes,
            created_by=self.ctx.user_id,
        )
        self.db.add(s)
        self.db.flush()
        self._sources[xref] = s
        self.counts["sources"] += 1
        return s

    def cite(self, citations: list[dict[str, Any]], target: CitationTarget, target_id: uuid.UUID) -> None:
        for c in citations or []:
            s = self.source(c["source"])
            if s is None:
                continue
            self.db.add(
                Citation(
                    tree_id=self.ctx.tree_id,
                    source_id=s.id,
                    target_type=target,
                    target_id=target_id,
                    page_or_image=c.get("page"),
                    text_excerpt=c.get("text"),
                    created_by=self.ctx.user_id,
                )
            )
            self.counts["citations"] += 1

    # ------------------------------------------------------------------ people
    def run(self) -> dict[str, Any]:
        individuals = self.staged.get("individuals", [])
        for ind in individuals:
            kind, pid = self.decisions.get(ind["xref"], (CREATE, None))
            if kind == SKIP:
                self.counts["people_skipped"] += 1
                continue
            if kind == ATTACH and pid is not None:
                self._attach(ind, pid)
            else:
                self._create(ind)
        self.db.flush()
        for fam in self.staged.get("families", []):
            self._family(fam)
        for rec in self.staged.get("preserved_records", []):
            self._preserve(None, "RECORD", rec)
        self.db.flush()
        return {"counts": dict(sorted(self.counts.items())), "warnings": self.warnings[:500]}

    def _names(self, person: Person, ind: dict[str, Any], *, attach: bool) -> list[Any]:
        out = []
        for n in ind["names"]:
            body = NameIn(
                type=n["type"],
                given_name=n.get("given"),
                surname=n.get("surname"),
                honorific_prefix=n.get("prefix"),
                honorific_suffix=n.get("suffix"),
                full_name_as_recorded=n.get("full"),
                language=n.get("language"),
                script=n.get("script"),
                is_preferred=bool(n.get("is_preferred")) and not attach,
            )
            rec = genealogy._new_name(self.ctx, person.id, body)
            for k, v in self.prov(ind["xref"], n.get("line")).items():
                setattr(rec, k, v)
            rec.is_preferred = body.is_preferred
            self.db.add(rec)
            out.append((rec, n))
            self.counts["names"] += 1
        self.db.flush()
        for rec, n in out:
            self.cite(n.get("citations", []), CitationTarget.NAME_RECORD, rec.id)
        return [r for r, _ in out]

    def _event(
        self,
        ev: dict[str, Any],
        principals: list[uuid.UUID],
        *,
        preferred: bool,
        xref: str,
    ) -> Event:
        date = ev.get("date")
        gd = GenealogicalDate.model_validate(date) if date else None
        lo, hi = gd.sort_range() if gd else (None, None)
        place = self.place(ev.get("place"))
        e = Event(
            tree_id=self.ctx.tree_id,
            type=EventType(ev["type"]),
            subtype=(ev.get("subtype") or None) and ev["subtype"][:80],
            date=date,
            date_sort_from=lo,
            date_sort_to=hi,
            time=ev.get("time"),
            timezone_id="UTC" if ev.get("utc") else None,
            utc_offset_minutes=0 if ev.get("utc") else None,
            place_id=place.id if place else None,
            place_as_recorded=ev.get("place"),
            latitude=ev.get("latitude"),
            longitude=ev.get("longitude"),
            reason=ev.get("reason"),
            description=ev.get("description"),
            is_preferred=preferred,
            evidence_status=EvidenceStatus.USER_ASSERTION,
            created_by=self.ctx.user_id,
            **self.prov(xref, ev.get("line")),
        )
        self.db.add(e)
        self.db.flush()
        for pid in dict.fromkeys(principals):
            self.db.add(
                EventParticipant(
                    tree_id=self.ctx.tree_id,
                    event_id=e.id,
                    person_id=pid,
                    role=ParticipantRole.PRINCIPAL,
                    created_by=self.ctx.user_id,
                )
            )
        self.counts["events"] += 1
        self.cite(ev.get("citations", []), CitationTarget.EVENT, e.id)
        return e

    def _person_events(self, person: Person, ind: dict[str, Any], *, attach: bool) -> None:
        seen_single: set[str] = set()
        for ev in ind["events"]:
            et = ev["type"]
            if attach:
                preferred = False
            elif et in (EventType.BIRTH.value, EventType.DEATH.value):
                preferred = et not in seen_single
                seen_single.add(et)
            else:
                preferred = True
            e = self._event(ev, [person.id], preferred=preferred, xref=ind["xref"])
            if et == EventType.BIRTH.value and preferred:
                self._births[person.id] = e.id
            if not attach:
                for p in ev.get("preserved", []):
                    self._preserve(person.id, "INDI", p)

    def _create(self, ind: dict[str, Any]) -> None:
        ctx = self.ctx
        resn = set(ind.get("resn") or [])
        privacy = ctx.tree.default_person_privacy
        if "CONFIDENTIAL" in resn:
            privacy = PrivacyLevel.PRIVATE_TREE_ADMINS
        status = ProfileStatus(ind.get("profile_status") or "unknown")
        if "PRIVACY" in resn and status == ProfileStatus.UNKNOWN:
            status = ProfileStatus.LIVING  # the file marks this person as privacy-restricted (living)
        notes = "\n\n".join(ind.get("notes") or []) or None
        person = Person(
            tree_id=ctx.tree_id,
            profile_status=status,
            preferred_display_name=(ind.get("display_name") or "Unnamed")[:300],
            sex_at_birth=SexAtBirth(ind["sex"]) if ind.get("sex") else None,
            privacy_level=privacy,
            occupation=ind.get("occupation"),
            notes=notes[:20000] if notes else None,
            created_by=ctx.user_id,
        )
        self.db.add(person)
        self.db.flush()
        self.person_map[ind["xref"]] = person.id
        self.people[person.id] = person
        self.created.add(ind["xref"])
        self.counts["people_created"] += 1
        names = self._names(person, ind, attach=False)
        preferred = next((n for n in names if n.is_preferred), names[0] if names else None)
        if preferred is not None:
            preferred.is_preferred = True
            person.preferred_display_name = name_display(preferred)[:300] or person.preferred_display_name
        person.scripts_used = sorted({n.script for n in names if n.script})
        self._person_events(person, ind, attach=False)
        self.cite(ind.get("citations", []), CitationTarget.PERSON, person.id)
        self._heritage(person, ind)
        self._astrology(person, ind)
        for p in ind.get("preserved", []):
            self._preserve(person.id, "INDI", p)

    def _attach(self, ind: dict[str, Any], pid: uuid.UUID) -> None:
        person = lookup.get_person(self.ctx, pid)
        self.person_map[ind["xref"]] = person.id
        self.people[person.id] = person
        self.attached.add(ind["xref"])
        self.counts["people_attached"] += 1
        self._names(person, ind, attach=True)
        self._person_events(person, ind, attach=True)
        skipped = (
            len(ind.get("heritage") or [])
            + (1 if ind.get("astrology") else 0)
            + len(ind.get("preserved") or [])
            + len(ind.get("citations") or [])
        )
        if skipped:
            self.counts["attach_facts_not_added"] += skipped
            self.warn(
                "attach_scope",
                "Only names and events are added to an attached person; heritage, astrology, "
                "person-level citations and extensions from the file were not applied",
                ind["xref"],
            )

    def _heritage(self, person: Person, ind: dict[str, Any]) -> None:
        seen: set[str] = set()
        for h in ind.get("heritage") or []:
            place = self.place(h["value"]) if h["attribute"] == "ancestral_village" else None
            a = Assertion(
                tree_id=self.ctx.tree_id,
                subject_type=AssertionSubject.PERSON,
                person_id=person.id,
                attribute=h["attribute"],
                value_text=h["value"],
                place_id=place.id if place else None,
                value_status=ValueStatus.KNOWN,
                evidence_status=EvidenceStatus.USER_ASSERTION,
                is_preferred=h["attribute"] not in seen,
                created_by=self.ctx.user_id,
                **self.prov(ind["xref"]),
            )
            seen.add(h["attribute"])
            self.db.add(a)
            self.db.flush()
            self.cite(h.get("citations", []), CitationTarget.ASSERTION, a.id)
            self.counts["heritage_assertions"] += 1

    def _astrology(self, person: Person, ind: dict[str, Any]) -> None:
        data = {k: v for k, v in (ind.get("astrology") or {}).items() if v is not None}
        if not data:
            return
        dropped: dict[str, Any] = {}
        body: AstrologyIn | None = None
        for _ in range(len(data) + 1):
            try:
                body = AstrologyIn(
                    provenance_kind=AstrologyProvenance.IMPORTED,
                    birth_event_id=self._births.get(person.id),
                    evidence_status=EvidenceStatus.USER_ASSERTION,
                    notes="As recorded in the GEDCOM file (not recognised): "
                    + ", ".join(f"{k}={v}" for k, v in dropped.items())
                    if dropped
                    else None,
                    **data,
                )
                break
            except ValidationError as exc:
                bad = {str(e["loc"][0]) for e in exc.errors() if e.get("loc")} & set(data)
                if not bad:
                    raise
                for k in bad:
                    dropped[k] = data.pop(k)
        if body is None:
            return
        if dropped:
            self.warn(
                "astrology_value",
                f"Unrecognised astrology value(s) kept as a note: {', '.join(sorted(dropped))}",
                ind["xref"],
            )
        astrology_service.create_profile(self.ctx, person.id, body, **self.prov(ind["xref"]))
        self.counts["astrology_profiles"] += 1

    def _preserve(self, person_id: uuid.UUID | None, record_type: str, p: dict[str, Any]) -> None:
        self.db.add(
            GedcomExtension(
                tree_id=self.ctx.tree_id,
                person_id=person_id,
                import_job_id=self.job.id,
                record_type=record_type[:20],
                tag=p["tag"][:80],
                uri=(p.get("uri") or None) and p["uri"][:500],
                payload=rewrite_pointers(p["payload"], self.person_map),
                created_by=self.ctx.user_id,
            )
        )
        self.counts["extensions_preserved"] += 1

    # ------------------------------------------------------------------ relationships
    def _relationship(
        self,
        a: uuid.UUID,
        b: uuid.UUID,
        rtype: RelationshipType,
        *,
        xref: str,
        union_id: uuid.UUID | None = None,
        subtype: str | None = None,
        evidence: EvidenceStatus = EvidenceStatus.USER_ASSERTION,
        start: dict[str, Any] | None = None,
        end: dict[str, Any] | None = None,
        order: int | None = None,
        notes: str | None = None,
    ) -> Relationship | None:
        if a == b:
            self.warn("self_relationship", "A person cannot be related to themselves; link skipped", xref)
            return None
        if rtype in SYMMETRIC_TYPES and str(a) > str(b):
            a, b = b, a
        key = (rtype.value, a, b)
        if key in self._rel_keys:
            return self._rel_keys[key]
        existing = self.db.scalar(
            select(Relationship).where(
                Relationship.tree_id == self.ctx.tree_id,
                Relationship.type == rtype,
                Relationship.person_a_id == a,
                Relationship.person_b_id == b,
            )
        )
        if existing is not None:
            self._rel_keys[key] = existing
            self.counts["relationships_existing"] += 1
            return existing
        if rtype in PARENT_TYPES:
            if genealogy.is_ancestor(self.ctx, b, a):
                self.warn(
                    "relationship_cycle", "Link skipped: it would make a person their own ancestor", xref
                )
                return None
            if rtype == RelationshipType.BIOLOGICAL_PARENT and evidence not in _BIO_EXCLUDED:
                if b not in self._bio_parents:
                    self._bio_parents[b] = (
                        self.db.scalar(
                            select(func.count())
                            .select_from(Relationship)
                            .where(
                                Relationship.tree_id == self.ctx.tree_id,
                                Relationship.person_b_id == b,
                                Relationship.type == RelationshipType.BIOLOGICAL_PARENT,
                                Relationship.evidence_status.notin_(list(_BIO_EXCLUDED)),
                            )
                        )
                        or 0
                    )
                if self._bio_parents[b] >= 2:
                    evidence = EvidenceStatus.DISPUTED
                    self.warn(
                        "too_many_biological_parents",
                        "More than two biological parents; the extra link was recorded as DISPUTED",
                        xref,
                    )
                else:
                    self._bio_parents[b] += 1
        rel = Relationship(
            tree_id=self.ctx.tree_id,
            person_a_id=a,
            person_b_id=b,
            type=rtype,
            subtype=subtype,
            lineage=DEFAULT_LINEAGE.get(rtype),
            union_id=union_id,
            start_date=start,
            end_date=end,
            union_order=order,
            notes=notes,
            evidence_status=evidence,
            created_by=self.ctx.user_id,
            **self.prov(xref),
        )
        self.db.add(rel)
        self.db.flush()
        self._rel_keys[key] = rel
        self._new_rels.add(rel.id)
        self.counts["relationships"] += 1
        return rel

    def _family(self, fam: dict[str, Any]) -> None:
        xref = fam["xref"]
        partner_x = [x for x in (fam.get("husb"), fam.get("wife")) if x]
        partners = [self.person_map[x] for x in partner_x if x in self.person_map]
        involves_attached = any(x in self.attached for x in partner_x)
        union: Relationship | None = None
        if len(partners) == 2 and partners[0] != partners[1]:
            rtype = RelationshipType(fam.get("relationship_type") or RelationshipType.SPOUSE.value)
            if rtype not in UNION_TYPES:
                rtype = RelationshipType.SPOUSE
            self._union_order[partners[0]] += 1
            union = self._relationship(
                partners[0],
                partners[1],
                rtype,
                xref=xref,
                start=fam.get("start_date"),
                end=fam.get("end_date"),
                order=self._union_order[partners[0]],
                notes="\n\n".join(fam.get("notes") or [])[:5000] or None,
            )
            if union is not None and union.id in self._new_rels:
                self.cite(fam.get("citations", []), CitationTarget.RELATIONSHIP, union.id)
        if partners:
            for ev in fam.get("events", []):
                self._event(ev, partners, preferred=not involves_attached, xref=xref)
        elif fam.get("events"):
            self.warn("family_without_partners", "Family events skipped: no imported partner", xref)
        owner = next((self.person_map[x] for x in partner_x if x in self.created), None)
        for p in fam.get("preserved", []):
            if owner is not None:
                self._preserve(owner, "FAM", p)
            else:
                self.counts["attach_facts_not_added"] += 1
        # children
        indis = {i["xref"]: i for i in self.staged.get("individuals", [])}
        roles = {x: role for x, role in ((fam.get("husb"), "HUSB"), (fam.get("wife"), "WIFE")) if x}
        for cx in fam.get("children", []):
            child = self.person_map.get(cx)
            if child is None:
                continue
            ind = indis.get(cx, {})
            link = next((f for f in ind.get("famc", []) if f["family"] == xref), None)
            adop = next(
                (
                    e["adoption_family"]
                    for e in ind.get("events", [])
                    if e.get("adoption_family") and e["adoption_family"]["family"] == xref
                ),
                None,
            )
            for px in partner_x:
                parent = self.person_map.get(px)
                if parent is None:
                    continue
                rtype, subtype, evidence = self._pedi(link)
                if adop and adop.get("by") in ("BOTH", roles.get(px)):
                    rtype, subtype = RelationshipType.ADOPTIVE_PARENT, None
                self._relationship(
                    parent,
                    child,
                    rtype,
                    xref=xref,
                    union_id=union.id if union is not None else None,
                    subtype=subtype,
                    evidence=evidence,
                )

    def _pedi(self, link: dict[str, Any] | None) -> tuple[RelationshipType, str | None, EvidenceStatus]:
        evidence = EvidenceStatus.USER_ASSERTION
        if link is None:
            return RelationshipType.BIOLOGICAL_PARENT, None, evidence
        status = link.get("status")
        if status == "DISPROVEN":
            evidence = EvidenceStatus.DISPROVEN
        elif status == "CHALLENGED":
            evidence = EvidenceStatus.DISPUTED
        pedi = (link.get("pedi") or "").upper()
        phrase = (link.get("pedi_phrase") or "").lower()
        if pedi in ("", "BIRTH"):
            return RelationshipType.BIOLOGICAL_PARENT, None, evidence
        if pedi == "ADOPTED":
            return RelationshipType.ADOPTIVE_PARENT, None, evidence
        if pedi == "FOSTER":
            return RelationshipType.FOSTER_PARENT, None, evidence
        if pedi == "OTHER" and phrase in ("step", "step_parent", "step-parent", "stepparent"):
            return RelationshipType.STEP_PARENT, None, evidence
        if pedi == "OTHER" and phrase == "guardian":
            return RelationshipType.GUARDIAN, None, evidence
        # SEALING / OTHER / unrecognised: recorded as biological, marked as such for review
        self.warn(
            "pedigree_other",
            f"Pedigree {pedi}{' (' + phrase + ')' if phrase else ''} recorded as a biological link for review",
        )
        return RelationshipType.BIOLOGICAL_PARENT, f"gedcom_pedi_{pedi.lower()}"[:80], evidence
