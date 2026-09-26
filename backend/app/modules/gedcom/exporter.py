"""GEDCOM 7.0 export from the exporter's privacy view (ADR-0006, ADR-0008).

Only people the caller can see are exported. Protected people (living, unknown-status born within
110 years, minors) are left out by default; with ``exclude_living=False`` they are included, but a
protected person whose full birth date the caller cannot see is reduced to a ``NAME Living``
placeholder that only keeps the family links. Event data goes through the genealogy Serializer, so
field redaction (year-only dates, hidden birth place/time, hidden residence detail) is identical to
the API. Sensitive groups (birth time, astrology, notes, contact/address, preserved unknown
extension payloads) are only written with ``include_sensitive=True``, which needs PRIVACY_MANAGE.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select

from app.authz.context import TreeContext
from app.authz.privacy import (
    FieldGroup,
    Subject,
    can_view_field,
    can_view_person,
    level_allows,
    load_subjects,
)
from app.core.dates import GenealogicalTime, TimePrecision
from app.models import (
    Assertion,
    AstrologyProfile,
    Citation,
    GedcomExtension,
    NameRecord,
    Person,
    Place,
    Relationship,
    Source,
)
from app.models.enums import (
    PARENT_TYPES,
    UNION_TYPES,
    CitationTarget,
    EventType,
    EvidenceStatus,
    NameType,
    ParticipantRole,
    PrivacyLevel,
    RelationshipType,
    SexAtBirth,
    ValueStatus,
)
from app.modules.astrology import service as astrology_service
from app.modules.evidence.service import can_view_source
from app.modules.gedcom import extensions as ext
from app.modules.gedcom.gdate import MONTHS, format_date, format_time
from app.modules.gedcom.mapping import OTHER_FAM_EVENTS, OTHER_INDI_EVENTS, STANDARD_ASSERTIONS
from app.modules.gedcom.parser import format_line
from app.modules.genealogy.schemas import EventOut
from app.modules.genealogy.serialize import Serializer

EVENT_TAGS = {
    EventType.BIRTH: "BIRT",
    EventType.DEATH: "DEAT",
    EventType.ADOPTION: "ADOP",
    EventType.RESIDENCE: "RESI",
    EventType.EDUCATION: "EDUC",
    EventType.OCCUPATION: "OCCU",
    EventType.CREMATION: "CREM",
    EventType.BURIAL: "BURI",
}
FAM_EVENT_TAGS = {EventType.MARRIAGE: "MARR", EventType.DIVORCE: "DIV", EventType.RESIDENCE: "RESI"}
ATTRIBUTE_TAGS = {"OCCU", "EDUC", "RESI"}  # payload carries the value
PEDI = {
    RelationshipType.BIOLOGICAL_PARENT: ("BIRTH", None),
    RelationshipType.ADOPTIVE_PARENT: ("ADOPTED", None),
    RelationshipType.FOSTER_PARENT: ("FOSTER", None),
    RelationshipType.STEP_PARENT: ("OTHER", "step"),
    RelationshipType.GUARDIAN: ("OTHER", "guardian"),
}
NAME_TYPE_OUT = {
    NameType.MARRIED: "MARRIED",
    NameType.ALIAS: "AKA",
    NameType.PROFESSIONAL: "PROFESSIONAL",
}
SEX_OUT = {SexAtBirth.MALE: "M", SexAtBirth.FEMALE: "F", SexAtBirth.INTERSEX: "X", SexAtBirth.UNKNOWN: "U"}
_DROPPED = (EvidenceStatus.DISPROVEN, EvidenceStatus.SUPERSEDED)
_VSH_POINTER = re.compile(r"^(\d+) ([A-Za-z0-9_]+) @VSH:([0-9a-f\-]{36})@$")
_ANY_POINTER = re.compile(r"^(\d+) ([A-Za-z0-9_]+) (@[^@]+@)$")


@dataclass
class _Fam:
    xref: str
    partners: list[uuid.UUID]
    union: Relationship | None = None
    children: list[tuple[uuid.UUID, RelationshipType]] = field(default_factory=list)


# heritage attribute → standard GEDCOM tag (the inverse of mapping.STANDARD_ASSERTIONS)
_STANDARD_TAG = {attr: tag for tag, attr in STANDARD_ASSERTIONS.items()}


class Exporter:
    def __init__(self, ctx: TreeContext, *, exclude_living: bool, include_sensitive: bool) -> None:
        self.ctx = ctx
        self.db = ctx.db
        self.exclude_living = exclude_living
        self.include_sensitive = include_sensitive
        self.lines: list[str] = []
        self.used_tags: set[str] = set()
        self.extra_schema: dict[str, str] = {}
        self.cited_sources: dict[uuid.UUID, str] = {}
        self.counts: dict[str, int] = defaultdict(int)

    # ------------------------------------------------------------------ helpers
    def emit(self, level: int, tag: str, value: str | None = None, xref: str | None = None) -> None:
        if tag.startswith("_IND_"):
            self.used_tags.add(tag)
        self.lines.extend(format_line(level, tag, value, xref))

    def sensitive_ok(self, s: Subject, group: str) -> bool:
        return self.include_sensitive and can_view_field(self.ctx, s, group)

    def source_xref(self, source_id: uuid.UUID) -> str:
        if source_id not in self.cited_sources:
            self.cited_sources[source_id] = f"@S{len(self.cited_sources) + 1}@"
        return self.cited_sources[source_id]

    def emit_citations(self, level: int, target: CitationTarget, target_id: uuid.UUID) -> None:
        for c in self.citations.get((target, target_id), []):
            if c.source_id not in self.sources:
                continue
            self.emit(level, "SOUR", self.source_xref(c.source_id))
            if c.page_or_image:
                self.emit(level + 1, "PAGE", c.page_or_image)
            if c.text_excerpt and self.include_sensitive:
                self.emit(level + 1, "DATA")
                self.emit(level + 2, "TEXT", c.text_excerpt)

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        ctx = self.ctx
        persons = self.db.scalars(
            select(Person)
            .where(Person.tree_id == ctx.tree_id, Person.deleted_at.is_(None))
            .order_by(Person.created_at, Person.id)
        ).all()
        subjects = load_subjects(ctx, persons)
        self.full: dict[uuid.UUID, Subject] = {}
        self.placeholders: dict[uuid.UUID, Subject] = {}
        for p in persons:
            s = subjects[p.id]
            if not can_view_person(ctx, s):
                continue
            if s.is_protected:
                if self.exclude_living:
                    self.counts["excluded_living"] += 1
                    continue
                if not can_view_field(ctx, s, FieldGroup.BIRTH_DATE_FULL):
                    self.placeholders[p.id] = s
                    continue
            self.full[p.id] = s
        self.order = [p.id for p in persons if p.id in self.full or p.id in self.placeholders]
        self.xref = {pid: f"@I{i + 1}@" for i, pid in enumerate(self.order)}
        ids = list(self.xref)
        full_ids = list(self.full)
        self.names: dict[uuid.UUID, list[NameRecord]] = defaultdict(list)
        if full_ids:
            for n in self.db.scalars(
                select(NameRecord)
                .where(NameRecord.tree_id == ctx.tree_id, NameRecord.person_id.in_(full_ids))
                .order_by(NameRecord.is_preferred.desc(), NameRecord.created_at, NameRecord.id)
            ):
                if n.evidence_status not in _DROPPED:
                    self.names[n.person_id].append(n)
        ser = Serializer(ctx)
        self.events: dict[uuid.UUID, list[EventOut]] = (
            ser.events_for(full_ids, dict(self.full)) if full_ids else {}
        )
        self.rels: list[Relationship] = []
        if ids:
            idset = set(ids)
            for r in self.db.scalars(
                select(Relationship)
                .where(Relationship.tree_id == ctx.tree_id, Relationship.person_a_id.in_(ids))
                .order_by(Relationship.union_order.nulls_last(), Relationship.created_at, Relationship.id)
            ):
                if r.person_b_id in idset and r.evidence_status not in _DROPPED:
                    self.rels.append(r)
        self.assertions: dict[uuid.UUID, list[Assertion]] = defaultdict(list)
        self.astrology: dict[uuid.UUID, AstrologyProfile] = {}
        self.extensions: dict[uuid.UUID | None, list[GedcomExtension]] = defaultdict(list)
        self.place_names: dict[uuid.UUID, str] = {}
        if full_ids:
            for a in self.db.scalars(
                select(Assertion)
                .where(
                    Assertion.tree_id == ctx.tree_id,
                    Assertion.person_id.in_(full_ids),
                    Assertion.is_preferred.is_(True),
                    Assertion.value_status == ValueStatus.KNOWN,
                )
                .order_by(Assertion.created_at)
            ):
                if (
                    a.attribute in ext.BY_ATTRIBUTE or a.attribute in _STANDARD_TAG
                ) and a.evidence_status not in _DROPPED:
                    self.assertions[a.person_id].append(a)  # type: ignore[index]
            place_ids = {a.place_id for lst in self.assertions.values() for a in lst if a.place_id}
            if place_ids:
                self.place_names = {
                    p.id: p.canonical_name
                    for p in self.db.scalars(
                        select(Place).where(Place.tree_id == ctx.tree_id, Place.id.in_(place_ids))
                    )
                }
            for ap in self.db.scalars(
                select(AstrologyProfile)
                .where(AstrologyProfile.tree_id == ctx.tree_id, AstrologyProfile.person_id.in_(full_ids))
                .order_by(AstrologyProfile.is_preferred.desc(), AstrologyProfile.created_at.desc())
            ):
                if ap.evidence_status not in _DROPPED:
                    self.astrology.setdefault(ap.person_id, ap)
        if self.include_sensitive:
            for e in self.db.scalars(
                select(GedcomExtension)
                .where(GedcomExtension.tree_id == ctx.tree_id)
                .order_by(GedcomExtension.created_at, GedcomExtension.id)
            ):
                if e.person_id is None or e.person_id in self.full:
                    self.extensions[e.person_id].append(e)
        # sources visible to the caller, and citations of exported objects
        self.sources = {
            s.id: s
            for s in self.db.scalars(select(Source).where(Source.tree_id == ctx.tree_id))
            if can_view_source(ctx, s)
        }
        self.citations: dict[tuple[CitationTarget, uuid.UUID], list[Citation]] = defaultdict(list)
        for c in self.db.scalars(
            select(Citation).where(Citation.tree_id == ctx.tree_id).order_by(Citation.created_at, Citation.id)
        ):
            self.citations[(c.target_type, c.target_id)].append(c)

    # ------------------------------------------------------------------ families
    def _build_families(self) -> None:
        exported = set(self.xref)
        self.fams: list[_Fam] = []
        self.fams_of: dict[uuid.UUID, list[str]] = defaultdict(list)
        self.famc_of: dict[uuid.UUID, list[tuple[str, RelationshipType]]] = defaultdict(list)
        by_union: dict[uuid.UUID, _Fam] = {}
        pair_union: dict[frozenset[uuid.UUID], _Fam] = {}
        for r in self.rels:
            if r.type not in UNION_TYPES:
                continue
            fam = _Fam(f"@F{len(self.fams) + 1}@", [r.person_a_id, r.person_b_id], r)
            self.fams.append(fam)
            by_union[r.id] = fam
            pair_union.setdefault(frozenset(fam.partners), fam)
        edges: dict[uuid.UUID, list[Relationship]] = defaultdict(list)
        for r in self.rels:
            if r.type in PARENT_TYPES and r.person_b_id in exported:
                edges[r.person_b_id].append(r)
        single: dict[uuid.UUID, _Fam] = {}

        def single_fam(parent: uuid.UUID) -> _Fam:
            if parent not in single:
                f = _Fam(f"@F{len(self.fams) + 1}@", [parent])
                self.fams.append(f)
                single[parent] = f
            return single[parent]

        for child, es in edges.items():
            loose: list[Relationship] = []
            groups: dict[uuid.UUID, list[Relationship]] = defaultdict(list)
            for e in es:
                if e.union_id and e.union_id in by_union:
                    groups[e.union_id].append(e)
                else:
                    loose.append(e)
            for uid, grp in groups.items():
                fam = by_union[uid]
                if len({e.type for e in grp}) == 1 and all(e.person_a_id in fam.partners for e in grp):
                    fam.children.append((child, grp[0].type))
                else:
                    loose.extend(grp)
            if len(loose) == 2 and loose[0].type == loose[1].type:
                fam_pair = pair_union.get(frozenset({loose[0].person_a_id, loose[1].person_a_id}))
                if fam_pair is not None and child not in {c for c, _ in fam_pair.children}:
                    fam_pair.children.append((child, loose[0].type))
                    loose = []
            for e in loose:
                single_fam(e.person_a_id).children.append((child, e.type))
        # drop union FAMs that would only reveal a hidden partner without adding anything
        kept: list[_Fam] = []
        for f in self.fams:
            f.partners = [p for p in f.partners if p in exported]
            if not f.partners and not f.children:
                continue
            if f.union is not None and len(f.partners) < 2 and not f.children:
                continue
            kept.append(f)
        for i, f in enumerate(kept):
            f.xref = f"@F{i + 1}@"
            for p in f.partners:
                self.fams_of[p].append(f.xref)
            for c, t in f.children:
                self.famc_of[c].append((f.xref, t))
        self.fams = kept

    # ------------------------------------------------------------------ events
    def _event_lines(self, level: int, tag: str, ev: EventOut, subject: Subject | None) -> None:
        value: str | None = None
        if tag in ATTRIBUTE_TAGS and ev.description:
            value = ev.description.split("\n", 1)[0][:248]
        has_detail = bool(ev.date or ev.place_name or ev.place_as_recorded)
        if value is None and tag not in ("EVEN",) and not has_detail:
            value = "Y"
        self.emit(level, tag, value)
        if tag == "EVEN":
            self.emit(level + 1, "TYPE", (ev.subtype or ev.type.value).replace("_", " "))
        elif ev.subtype and ev.type != EventType.MIGRATION and ev.type != EventType.OTHER:
            self.emit(level + 1, "TYPE", ev.subtype)
        time_text = None
        if (
            ev.time
            and subject is not None
            and (ev.type != EventType.BIRTH or self.sensitive_ok(subject, FieldGroup.BIRTH_TIME))
        ):
            time_text = format_time(ev.time, utc=ev.timezone_id in ("UTC", "Etc/UTC"))
        fd = format_date(ev.date)
        if fd is not None or time_text:
            payload, phrase = fd if fd is not None else ("", None)
            self.emit(level + 1, "DATE", payload or None)
            if time_text:
                self.emit(level + 2, "TIME", time_text)
            if phrase:
                self.emit(level + 2, "PHRASE", phrase)
        place = ev.place_as_recorded or ev.place_name
        if place:
            self.emit(level + 1, "PLAC", place.replace("\n", " "))
            if ev.latitude is not None and ev.longitude is not None:
                self.emit(level + 2, "MAP")
                self.emit(level + 3, "LATI", f"{'N' if ev.latitude >= 0 else 'S'}{abs(ev.latitude):.6f}")
                self.emit(level + 3, "LONG", f"{'E' if ev.longitude >= 0 else 'W'}{abs(ev.longitude):.6f}")
        if ev.reason:
            self.emit(level + 1, "CAUS", ev.reason.split("\n", 1)[0][:248])
        if ev.description and (tag not in ATTRIBUTE_TAGS or "\n" in ev.description):
            self.emit(level + 1, "NOTE", ev.description)
        if ev.type == EventType.BIRTH and time_text and ev.time:
            t = GenealogicalTime.model_validate(ev.time)
            if t.precision != TimePrecision.UNKNOWN or t.source.value != "unknown":
                self.emit(level + 1, "_IND_BIRTH_TIME_CONF", f"{t.precision.value} {t.source.value}")
        self.emit_citations(level + 1, CitationTarget.EVENT, ev.id)
        self.counts["events"] += 1

    def _event_tag(self, ev: EventOut) -> str:
        if ev.type in EVENT_TAGS:
            return EVENT_TAGS[ev.type]
        if ev.type == EventType.MIGRATION:
            return "IMMI" if (ev.subtype or "").lower().startswith("immig") else "EMIG"
        if ev.type == EventType.OTHER and ev.subtype and ev.subtype.upper() in OTHER_INDI_EVENTS:
            return ev.subtype.upper()
        return "EVEN"

    # ------------------------------------------------------------------ names
    @staticmethod
    def _name_payload(n: NameRecord) -> str:
        given = " ".join(p for p in (n.given_name, n.middle_names) if p)
        if not given and not n.surname:
            return (n.full_name_as_recorded or n.romanized_value or "Unnamed").replace("/", " ")
        parts = [n.honorific_prefix, given or None]
        text = " ".join(p for p in parts if p)
        text = f"{text} /{n.surname or ''}/" if n.surname else text
        if n.honorific_suffix:
            text = f"{text} {n.honorific_suffix}"
        return text.strip()

    def _name_pieces(self, level: int, n: NameRecord) -> None:
        given = " ".join(p for p in (n.given_name, n.middle_names) if p)
        if n.honorific_prefix:
            self.emit(level, "NPFX", n.honorific_prefix)
        if given:
            self.emit(level, "GIVN", given)
        if n.surname:
            self.emit(level, "SURN", n.surname)
        if n.honorific_suffix:
            self.emit(level, "NSFX", n.honorific_suffix)

    @staticmethod
    def _lang(n: NameRecord) -> str:
        lang = (n.language or "").strip()
        script = (n.script or "").strip()
        if lang and "-" in lang:
            return lang
        if lang:
            return f"{lang}-{script}" if script and script != "Latn" else lang
        return f"und-{script}" if script else "und"

    def _names(self, pid: uuid.UUID) -> None:
        names = self.names.get(pid, [])
        if not names:
            self.emit(1, "NAME", self.full[pid].person.preferred_display_name)
            return
        host = names[0]
        host_script = host.script or "Latn"
        trans = [n for n in names[1:] if n.script and n.script != "Latn" and n.script != host_script]
        for n in [host] + [n for n in names[1:] if n not in trans]:
            self.emit(1, "NAME", self._name_payload(n))
            if n.type in NAME_TYPE_OUT:
                self.emit(2, "TYPE", NAME_TYPE_OUT[n.type])
            elif n.type != NameType.BIRTH:
                self.emit(2, "TYPE", "OTHER")
                self.emit(3, "PHRASE", n.type.value)
            self._name_pieces(2, n)
            if n is host:
                for t in trans:
                    self.emit(2, "TRAN", self._name_payload(t))
                    self.emit(3, "LANG", self._lang(t))
                    self._name_pieces(3, t)
            self.emit_citations(2, CitationTarget.NAME_RECORD, n.id)

    # ------------------------------------------------------------------ extensions
    def _preserved(self, base: int, e: GedcomExtension) -> None:
        if e.uri:
            first_tag = e.tag.split(".")[-1]
            if first_tag.startswith("_") and not first_tag.startswith("_IND_"):
                self.extra_schema.setdefault(first_tag, e.uri)
        for ln in e.payload.split("\n"):
            m = _VSH_POINTER.match(ln)
            if m:
                target = self.xref.get(uuid.UUID(m.group(3)), "@VOID@")
                ln = f"{m.group(1)} {m.group(2)} {target}"
            else:
                mp = _ANY_POINTER.match(ln)
                if mp and mp.group(3) != "@VOID@":
                    ln = f"{mp.group(1)} {mp.group(2)} @VOID@"
            lvl, _, rest = ln.partition(" ")
            if not lvl.isdigit():
                continue
            if rest.startswith("_IND_"):
                self.used_tags.add(rest.split(" ", 1)[0])
            self.lines.append(f"{int(lvl) + base} {rest}")
        self.counts["extensions"] += 1

    def _heritage(self, s: Subject) -> None:
        heritage_ok = can_view_field(self.ctx, s, FieldGroup.HERITAGE)
        for a in self.assertions.get(s.id, []):
            if a.privacy_level is not None and not level_allows(self.ctx, a.privacy_level, subject=s):
                continue
            if a.attribute in _STANDARD_TAG:
                # religion is sensitive: exported only with sensitive fields, like any preserved RELI
                if not self.sensitive_ok(s, FieldGroup.RELIGION):
                    continue
                tag = _STANDARD_TAG[a.attribute]
            elif heritage_ok:
                tag = ext.BY_ATTRIBUTE[a.attribute].tag
            else:
                continue
            value = a.value_text or (self.place_names.get(a.place_id) if a.place_id else None)
            if not value:
                continue
            self.emit(1, tag, value)
            self.emit_citations(2, CitationTarget.ASSERTION, a.id)

    def _astrology(self, s: Subject) -> None:
        ap = self.astrology.get(s.id)
        if (
            ap is None
            or not self.include_sensitive
            or not astrology_service.can_view_profile(self.ctx, ap, s)
        ):
            return
        for d in ext.ASTROLOGY_FIELDS:
            v = getattr(ap, d.target or "", None)
            if v is not None and v != "":
                self.emit(1, d.tag, str(v))

    # ------------------------------------------------------------------ records
    def _indi(self, pid: uuid.UUID) -> None:
        xref = self.xref[pid]
        if pid in self.placeholders:
            self.emit(0, "INDI", xref=xref)
            self.emit(1, "NAME", "Living")
            self.emit(1, "RESN", "PRIVACY")
            self._family_links(pid)
            self.counts["placeholders"] += 1
            return
        s = self.full[pid]
        p = s.person
        self.emit(0, "INDI", xref=xref)
        if p.privacy_level in (
            PrivacyLevel.PRIVATE_SELF,
            PrivacyLevel.PRIVATE_TREE_ADMINS,
            PrivacyLevel.CUSTOM,
        ):
            self.emit(1, "RESN", "CONFIDENTIAL")
        elif s.is_protected:
            self.emit(1, "RESN", "PRIVACY")
        self._names(pid)
        self.emit(1, "SEX", SEX_OUT.get(p.sex_at_birth, "U") if p.sex_at_birth else "U")  # type: ignore[arg-type]
        nested: dict[str, list[GedcomExtension]] = defaultdict(list)
        for e in self.extensions.get(pid, []):
            if e.record_type == "INDI" and "." in e.tag:
                nested[e.tag.split(".", 1)[0]].append(e)
        has_occu_event = False
        for ev in self.events.get(pid, []):
            principals = [x.person_id for x in ev.participants if x.role == ParticipantRole.PRINCIPAL]
            if pid not in principals or ev.id in self.fam_event_ids:
                continue
            if ev.type == EventType.RESIDENCE and not self.sensitive_ok(s, FieldGroup.ADDRESS):
                continue
            # a couple event without an exported FAM can only be an INDI EVEN in GEDCOM 7
            couple = ev.type in (EventType.MARRIAGE, EventType.DIVORCE)
            tag = "EVEN" if couple else self._event_tag(ev)
            has_occu_event |= tag == "OCCU"
            self._event_lines(1, tag, ev, s)
            for pe in nested.pop(tag, []):
                self._preserved(2, pe)
        if p.occupation and not has_occu_event:
            self.emit(1, "OCCU", p.occupation)
        self._family_links(pid)
        self._heritage(s)
        self._astrology(s)
        if p.notes and self.sensitive_ok(s, FieldGroup.NOTES):
            self.emit(1, "NOTE", p.notes)
        self.emit_citations(1, CitationTarget.PERSON, pid)
        for e in self.extensions.get(pid, []):
            if e.record_type == "INDI" and "." not in e.tag:
                self._preserved(1, e)
        self.counts["people"] += 1

    def _family_links(self, pid: uuid.UUID) -> None:
        for fx, t in self.famc_of.get(pid, []):
            self.emit(1, "FAMC", fx)
            pedi, phrase = PEDI.get(t, ("OTHER", t.value))
            self.emit(2, "PEDI", pedi)
            if phrase:
                self.emit(3, "PHRASE", phrase)
        for fx in self.fams_of.get(pid, []):
            self.emit(1, "FAMS", fx)

    def _fam_events(self) -> None:
        """Couple events (two principals who form an exported FAM) go under the FAM."""
        self.fam_event_ids: set[uuid.UUID] = set()
        self.fam_events: dict[str, list[EventOut]] = defaultdict(list)
        pair_to_fam = {frozenset(f.partners): f for f in self.fams if len(f.partners) == 2}
        seen: set[uuid.UUID] = set()
        for evs in self.events.values():
            for ev in evs:
                if ev.id in seen:
                    continue
                seen.add(ev.id)
                principals = frozenset(
                    x.person_id for x in ev.participants if x.role == ParticipantRole.PRINCIPAL
                )
                fam = pair_to_fam.get(principals)
                if fam is None:
                    continue
                if any(p in self.placeholders or p not in self.full for p in principals):
                    continue
                if ev.type in FAM_EVENT_TAGS or ev.type == EventType.OTHER:
                    self.fam_event_ids.add(ev.id)
                    self.fam_events[fam.xref].append(ev)

    def _fam(self, f: _Fam, emitted_ext: set[uuid.UUID]) -> None:
        self.emit(0, "FAM", xref=f.xref)
        slots: dict[str, uuid.UUID] = {}
        partners = [p for p in f.partners if p in self.xref]
        for p in partners:
            sex = self.full[p].person.sex_at_birth if p in self.full else None
            pref = "WIFE" if sex == SexAtBirth.FEMALE else "HUSB"
            other = "HUSB" if pref == "WIFE" else "WIFE"
            slot = pref if pref not in slots else other
            slots[slot] = p
        for slot in ("HUSB", "WIFE"):
            if slot in slots:
                self.emit(1, slot, self.xref[slots[slot]])
        for c, _t in f.children:
            self.emit(1, "CHIL", self.xref[c])
        evs = self.fam_events.get(f.xref, [])
        for ev in evs:
            if ev.type in FAM_EVENT_TAGS:
                tag = FAM_EVENT_TAGS[ev.type]
            elif ev.subtype and ev.subtype.upper() in OTHER_FAM_EVENTS:
                tag = ev.subtype.upper()
            else:
                tag = "EVEN"
            self._event_lines(1, tag, ev, None)
        u = f.union
        if u is not None:
            kinds = {e.type for e in evs}
            if u.type == RelationshipType.DIVORCED_SPOUSE and EventType.DIVORCE not in kinds:
                self.emit(1, "DIV", "Y")
            elif u.type == RelationshipType.SEPARATED_SPOUSE and not any(
                (e.subtype or "").lower() in ("separation", "separated") for e in evs
            ):
                self.emit(1, "EVEN")
                self.emit(2, "TYPE", "Separation")
            elif u.type == RelationshipType.PARTNER and EventType.MARRIAGE not in kinds:
                self.emit(1, "NO", "MARR")
            if u.notes and self.include_sensitive:
                self.emit(1, "NOTE", u.notes)
            self.emit_citations(1, CitationTarget.RELATIONSHIP, u.id)
            if len(partners) == 2 and all(p in self.full for p in partners):
                for p in partners:
                    for e in self.extensions.get(p, []):
                        if e.record_type == "FAM" and e.id not in emitted_ext:
                            emitted_ext.add(e.id)
                            if "." in e.tag:
                                continue  # nested in a family event: not re-attached
                            self._preserved(1, e)
        self.counts["families"] += 1

    def _sources(self) -> list[str]:
        body_lines = self.lines
        self.lines = []
        repos: dict[str, str] = {}
        for sid, sx in list(self.cited_sources.items()):
            s = self.sources[sid]
            self.emit(0, "SOUR", xref=sx)
            self.emit(1, "TITL", s.title)
            if s.issuing_authority:
                self.emit(1, "AUTH", s.issuing_authority)
            if s.transcription:
                self.emit(1, "TEXT", s.transcription)
            if s.repository:
                rx = repos.setdefault(s.repository, f"@R{len(repos) + 1}@")
                self.emit(1, "REPO", rx)
                if s.record_number:
                    self.emit(2, "CALN", s.record_number)
            if s.notes and self.include_sensitive:
                self.emit(1, "NOTE", s.notes)
            self.counts["sources"] += 1
        for name, rx in repos.items():
            self.emit(0, "REPO", xref=rx)
            self.emit(1, "NAME", name)
        src_lines = self.lines
        self.lines = body_lines
        return src_lines

    def _head(self) -> list[str]:
        today = dt.date.today()
        out: list[str] = ["0 HEAD", "1 GEDC", "2 VERS 7.0"]
        schema = ext.schema_lines(self.used_tags)
        if schema or self.extra_schema:
            out.append("1 SCHMA")
            for tag, uri in schema:
                out.append(f"2 TAG {tag} {uri}")
            for tag, uri in sorted(self.extra_schema.items()):
                out.append(f"2 TAG {tag} {uri}")
        out += [
            "1 SOUR Vanshavali",
            "2 NAME Vanshavali",
            f"1 DATE {today.day} {MONTHS[today.month - 1]} {today.year}",
        ]
        return out

    # ------------------------------------------------------------------ run
    def run(self) -> tuple[bytes, dict[str, int]]:
        self._load()
        self._build_families()
        self._fam_events()
        for pid in self.order:
            self._indi(pid)
        emitted_ext: set[uuid.UUID] = set()
        for f in self.fams:
            self._fam(f, emitted_ext)
        for e in self.extensions.get(None, []):
            if e.record_type == "RECORD":
                self._preserved(0, e)
        src = self._sources()
        text = "\n".join([*self._head(), *self.lines, *src, "0 TRLR"]) + "\n"
        return text.encode("utf-8"), dict(self.counts)
