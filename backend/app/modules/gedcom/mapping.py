"""Map a parsed GEDCOM tree onto the staging JSON (``ImportJob.staged``) and build the report.

Staging is pure (no database access): it converts names, dates, places, families, sources, notes
and the Indian ``_IND_*`` extensions into plain JSON that the preview shows and the commit step
writes. Unknown extension structures (and standard structures we do not model) are kept verbatim
as GEDCOM lines so they can be stored in ``gedcom_extension`` and re-emitted on export.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from typing import Any

from app.core.dates import GenealogicalDate, TimePrecision, TimeSource
from app.core.textnorm import detect_script
from app.models.enums import EventType, HeritageAttribute, NameType, RelationshipType
from app.modules.gedcom import extensions as ext
from app.modules.gedcom.gdate import parse_date, parse_time, time_precision_valid
from app.modules.gedcom.parser import Node, ParseResult, head_schema, node_lines

PRESUMED_LIVING_YEARS = 110

INDI_EVENTS: dict[str, tuple[EventType, str | None]] = {
    "BIRT": (EventType.BIRTH, None),
    "DEAT": (EventType.DEATH, None),
    "ADOP": (EventType.ADOPTION, None),
    "RESI": (EventType.RESIDENCE, None),
    "EMIG": (EventType.MIGRATION, "emigration"),
    "IMMI": (EventType.MIGRATION, "immigration"),
    "EDUC": (EventType.EDUCATION, None),
    "OCCU": (EventType.OCCUPATION, None),
    "CREM": (EventType.CREMATION, None),
    "BURI": (EventType.BURIAL, None),
}
# standard individual events without a dedicated EventType: kept as OTHER with the tag as subtype
OTHER_INDI_EVENTS = frozenset(
    {
        "CHR", "CHRA", "BAPM", "BARM", "BASM", "BLES", "CONF", "FCOM", "ORDN", "NATU", "CENS", "PROB",
        "WILL", "GRAD", "RETI",
    }
)  # fmt: skip
FAM_EVENTS: dict[str, tuple[EventType, str | None]] = {
    "MARR": (EventType.MARRIAGE, None),
    "DIV": (EventType.DIVORCE, None),
    "RESI": (EventType.RESIDENCE, None),
}
OTHER_FAM_EVENTS = frozenset({"ANUL", "DIVF", "ENGA", "MARB", "MARC", "MARL", "MARS", "CENS"})
# Standard GEDCOM attributes that are explicit statements about a heritage field. They become
# heritage assertions (user assertions with import provenance); nothing is ever inferred from them.
STANDARD_ASSERTIONS: dict[str, str] = {"RELI": HeritageAttribute.RELIGION.value}

MAX_PHOTOS_PER_PERSON = 50

# Structure an INDI record may carry and still be only a photo container (see _is_photo_container).
_PHOTO_CONTAINER_TAGS = frozenset({"OBJE", "RIN", "_UID", "_UPD", "SEX", "CHAN", "UID", "REFN"})

IGNORED_TAGS = frozenset(
    {"CHAN", "CREA", "RIN", "RFN", "AFN", "REFN", "UID", "EXID", "SUBM", "ANCI", "DESI", "_UID"}
)
NAME_TYPES = {
    "BIRTH": NameType.BIRTH,
    "MAIDEN": NameType.BIRTH,
    "MARRIED": NameType.MARRIED,
    "AKA": NameType.ALIAS,
    "ALIAS": NameType.ALIAS,
    "IMMIGRANT": NameType.ALIAS,
    "PROFESSIONAL": NameType.PROFESSIONAL,
}
PEDI_VALUES = {"BIRTH", "ADOPTED", "FOSTER", "SEALING", "OTHER"}
SEX = {"M": "male", "F": "female", "X": "intersex", "U": "unknown"}

MAX_TEXT = 5000


def _clip(v: str | None, n: int) -> str | None:
    if v is None:
        return None
    v = re.sub(r"[ \t]+", " ", v).strip()
    return v[:n] if v else None


def parse_lang(lang: str | None) -> tuple[str | None, str | None]:
    """BCP 47 tag → (language, ISO 15924 script). ``und-Deva`` → (None, "Deva")."""
    if not lang:
        return None, None
    parts = re.split(r"[-_]", lang.strip())
    language = parts[0].lower() if parts and parts[0] else None
    script = None
    for p in parts[1:]:
        if len(p) == 4 and p.isalpha():
            script = p.title()
            break
    if language in ("und", "mul", "zxx", ""):
        language = None
    return (language[:16] if language else None), script


class Stager:
    def __init__(self, result: ParseResult, today: dt.date | None = None) -> None:
        self.result = result
        self.today = today or dt.date.today()
        self.schema = head_schema(result)
        self.warnings: list[dict[str, Any]] = [i.as_dict() for i in result.issues]
        self.ext_used: Counter[str] = Counter()
        self.unknown_ext: Counter[str] = Counter()
        self.unsupported: Counter[str] = Counter()
        self.media_refs = 0
        self.media_records: dict[str, Node] = {}  # top-level OBJE records, for pointers
        self.photos_unlinked = 0  # media held by records that are not people (ADR-0013)
        self.places: set[str] = set()
        self.notes_index: dict[str, str] = {}
        self.repos: dict[str, str] = {}
        self.sources: dict[str, dict[str, Any]] = {}
        self._inline_sources = 0
        self.citation_count = 0
        self.note_count = 0
        self.preserved_count = 0

    # ------------------------------------------------------------------ helpers
    def warn(self, line: int | None, code: str, message: str) -> None:
        self.warnings.append({"line": line, "code": code, "message": message, "severity": "warning"})

    def _preserve(self, node: Node, prefix: str | None = None) -> dict[str, Any]:
        self.preserved_count += 1
        tag = node.tag if prefix is None else f"{prefix}.{node.tag}"
        return {
            "tag": tag[:80],
            "uri": self.schema.get(node.tag),
            "payload": "\n".join(node_lines(Node(0, node.tag, node.value, None, node.line, node.children))),
            "line": node.line,
        }

    def _unhandled(self, node: Node, context: str, *, preserve: bool) -> dict[str, Any] | None:
        if node.tag in IGNORED_TAGS:
            return None
        if node.tag.startswith("_"):
            self.unknown_ext[node.tag] += 1
        else:
            self.unsupported[node.tag] += 1
        if preserve:
            return self._preserve(node, None if context in ("INDI", "FAM", "RECORD") else context)
        return None

    def _note_text(self, node: Node) -> str | None:
        ptr = node.pointer
        if ptr:
            text = self.notes_index.get(ptr)
            if text is None:
                self.warn(node.line, "dangling_pointer", f"Note {ptr} is not defined")
            return text
        self.note_count += 1
        return node.value

    def _citation(self, node: Node) -> dict[str, Any] | None:
        ptr = node.pointer
        if ptr is None:
            if not node.value:
                return None
            # GEDCOM 5.5.1 inline source (a description, not a pointer)
            self._inline_sources += 1
            ptr = f"@_INLINE{self._inline_sources}@"
            self.sources[ptr] = {
                "xref": ptr,
                "title": _clip(node.value.split("\n", 1)[0], 400) or "Untitled source",
                "text": _clip(node.value, MAX_TEXT),
                "line": node.line,
            }
        elif ptr not in self.sources:
            self.warn(node.line, "dangling_pointer", f"Source {ptr} is not defined")
            return None
        self.citation_count += 1
        data = node.first("DATA")
        text = data.val("TEXT") if data is not None else None
        return {"source": ptr, "page": _clip(node.val("PAGE"), 200), "text": _clip(text, MAX_TEXT)}

    def _citations(self, node: Node) -> list[dict[str, Any]]:
        out = []
        for s in node.all("SOUR"):
            c = self._citation(s)
            if c:
                out.append(c)
        return out

    def _media(self, node: Node) -> None:
        self.media_refs += len(node.all("OBJE"))

    def _media_list(self, node: Node) -> list[dict[str, Any]]:
        """A person's photos: inline OBJE, or pointers to top-level OBJE records (ADR-0013).

        GEDCOM 5.5.1 puts FORM/TITL next to FILE or under it; GEDCOM 7 puts them under FILE.
        """
        out: list[dict[str, Any]] = []
        for o in node.all("OBJE"):
            rec = self.media_records.get(o.pointer or "") if o.pointer else o
            if rec is None:
                if o.pointer:
                    self.warn(o.line, "dangling_pointer", f"Media object {o.pointer} is not defined")
                continue
            files = []
            for f in rec.all("FILE"):
                path = (f.value or "").strip()
                if not path:
                    continue
                files.append(
                    {
                        "file": _clip(path, 1000),
                        "form": _clip(f.val("FORM") or rec.val("FORM"), 60),
                        "title": _clip(f.val("TITL") or rec.val("TITL"), 300),
                    }
                )
            if files:
                out.append(
                    {
                        "files": files[:10],
                        "primary": (o.val("_PRIM") or rec.val("_PRIM") or "").upper() == "Y",
                    }
                )
        return out[:MAX_PHOTOS_PER_PERSON]

    # ------------------------------------------------------------------ top level
    def run(self) -> tuple[dict[str, Any], dict[str, Any]]:
        records = self.result.records
        # indexes first: notes, repositories, sources (so pointers resolve regardless of order)
        for r in records:
            if r.tag in ("SNOTE", "NOTE") and r.xref:
                self.notes_index[r.xref] = r.value or ""
                self.note_count += 1
            elif r.tag == "REPO" and r.xref:
                self.repos[r.xref] = _clip(r.val("NAME"), 300) or ""
            elif r.tag == "OBJE" and r.xref:
                self.media_records[r.xref] = r
        for r in records:
            if r.tag == "SOUR":
                self._stage_source(r)
        individuals: list[dict[str, Any]] = []
        families: list[dict[str, Any]] = []
        preserved_records: list[dict[str, Any]] = []
        seen_xrefs: set[str] = set()
        anon = 0
        for r in records:
            if r.tag == "INDI" and _is_photo_container(r):
                # e.g. MyHeritage's "Unassociated photos" pseudo-person: not a person, never staged
                self.media_refs += len(r.all("OBJE"))
                self.photos_unlinked += sum(len(m["files"]) for m in self._media_list(r))
                self.warn(
                    r.line,
                    "photo_container_skipped",
                    f"{r.xref or 'An INDI record'} only holds photos that are not linked to anyone "
                    '(e.g. MyHeritage\'s "Unassociated photos"); it was not imported as a person',
                )
                continue
            if r.tag in ("INDI", "FAM"):
                xref = r.xref
                if not xref or xref in seen_xrefs:
                    anon += 1
                    self.warn(r.line, "missing_xref", f"{r.tag} record without a unique cross-reference id")
                    xref = f"@_ANON{anon}@"
                seen_xrefs.add(xref)
                if r.tag == "INDI":
                    individuals.append(self._stage_indi(r, xref))
                else:
                    families.append(self._stage_fam(r, xref))
            elif r.tag == "OBJE":
                self.media_refs += 1
            elif r.tag in ("HEAD", "TRLR", "SOUR", "SNOTE", "NOTE", "REPO", "SUBM", "SUBN"):
                continue
            elif r.tag.startswith("_"):
                self.unknown_ext[r.tag] += 1
                preserved_records.append(self._preserve(r))
            else:
                self.unsupported[r.tag] += 1
        self._link_families(individuals, families)
        staged = {
            "version": self.result.version,
            "encoding": self.result.encoding,
            "schema": self.schema,
            "individuals": individuals,
            "families": families,
            "sources": list(self.sources.values()),
            "preserved_records": preserved_records,
        }
        report = {
            "version": self.result.version,
            "encoding": self.result.encoding,
            "truncated": self.result.truncated,
            "counts": {
                "people": len(individuals),
                "families": len(families),
                "events": sum(len(i["events"]) for i in individuals)
                + sum(len(f["events"]) for f in families),
                "names": sum(len(i["names"]) for i in individuals),
                "places": len(self.places),
                "sources": len(self.sources),
                "citations": self.citation_count,
                "media_refs": self.media_refs,
                "notes": self.note_count,
                "repositories": len(self.repos),
                "preserved_structures": self.preserved_count,
                "photos_unlinked": self.photos_unlinked,
            },
            "extension_tags": dict(sorted(self.ext_used.items())),
            "unknown_extension_tags": dict(sorted(self.unknown_ext.items())),
            "unsupported_tags": dict(sorted(self.unsupported.items())),
            "warnings": [w for w in self.warnings if w.get("severity") != "error"],
            "errors": [w for w in self.warnings if w.get("severity") == "error"],
        }
        return staged, report

    # ------------------------------------------------------------------ sources
    def _stage_source(self, r: Node) -> None:
        xref = r.xref or f"@_SOUR{len(self.sources) + 1}@"
        repo_name = None
        repo = r.first("REPO")
        if repo is not None:
            repo_name = self.repos.get(repo.pointer or "") or _clip(repo.value, 300)
        notes = [t for t in (self._note_text(n) for n in r.all("NOTE") + r.all("SNOTE")) if t]
        self._media(r)
        self.sources[xref] = {
            "xref": xref,
            "title": _clip(r.val("TITL") or r.val("ABBR") or r.value, 400) or "Untitled source",
            "author": _clip(r.val("AUTH"), 300),
            "publication": _clip(r.val("PUBL"), 2000),
            "text": _clip(r.val("TEXT"), MAX_TEXT),
            "repository": repo_name,
            "notes": _clip("\n\n".join(notes), MAX_TEXT),
            "line": r.line,
        }

    # ------------------------------------------------------------------ names
    def _name_pieces(self, node: Node, payload: str | None) -> dict[str, Any]:
        given = surname = suffix_text = None
        full = None
        if payload:
            m = re.match(r"^(.*?)/(.*?)/(.*)$", payload)
            if m:
                given = _clip(m.group(1), 200)
                surname = _clip(m.group(2), 200)
                suffix_text = _clip(m.group(3), 80)
            full = _clip(payload.replace("/", " "), 500)
        givn, surn, spfx = node.val("GIVN"), node.val("SURN"), node.val("SPFX")
        if givn:
            given = _clip(givn, 200)
        if surn:
            surname = _clip(f"{spfx} {surn}" if spfx else surn, 200)
        return {
            "given": given,
            "surname": surname,
            "prefix": _clip(node.val("NPFX"), 80),
            "suffix": _clip(node.val("NSFX"), 80) or suffix_text,
            "full": full,
        }

    def _stage_names(self, indi: Node) -> list[dict[str, Any]]:
        names: list[dict[str, Any]] = []
        for i, n in enumerate(indi.all("NAME")):
            type_node = n.first("TYPE")
            ntype = NameType.BIRTH
            if type_node is not None and type_node.value:
                tv = type_node.value.strip().upper()
                phrase = (type_node.val("PHRASE") or "").strip().lower()
                if tv == "OTHER" and phrase in {t.value for t in NameType}:
                    ntype = NameType(phrase)
                else:
                    ntype = NAME_TYPES.get(tv, NameType.ALIAS)
            pieces = self._name_pieces(n, n.value)
            if not any(pieces[k] for k in ("given", "surname", "full")):
                self.warn(n.line, "empty_name", "Empty NAME ignored")
                continue
            base = {
                **pieces,
                "type": ntype.value,
                "language": None,
                "script": detect_script(pieces["full"] or ""),
                "is_preferred": not names,
                "citations": self._citations(n),
                "line": n.line,
            }
            names.append(base)
            nick = n.val("NICK")
            if nick:
                names.append(
                    {
                        "given": _clip(nick, 200),
                        "surname": None,
                        "prefix": None,
                        "suffix": None,
                        "full": _clip(nick, 500),
                        "type": NameType.NICKNAME.value,
                        "language": None,
                        "script": detect_script(nick),
                        "is_preferred": False,
                        "citations": [],
                        "line": n.line,
                    }
                )
            for tr in n.all("TRAN"):
                tp = self._name_pieces(tr, tr.value)
                if not any(tp[k] for k in ("given", "surname", "full")):
                    continue
                language, script = parse_lang(tr.val("LANG"))
                names.append(
                    {
                        **tp,
                        "type": ntype.value,
                        "language": language,
                        "script": script or detect_script(tp["full"] or ""),
                        "is_preferred": False,
                        "citations": [],
                        "line": tr.line,
                        "translation_of": i,
                    }
                )
            for c in n.children:
                if c.tag not in (
                    "TYPE",
                    "GIVN",
                    "SURN",
                    "SPFX",
                    "NPFX",
                    "NSFX",
                    "NICK",
                    "TRAN",
                    "SOUR",
                    "NOTE",
                ):
                    self._unhandled(c, "NAME", preserve=False)
        return names

    # ------------------------------------------------------------------ events
    def _stage_event(self, node: Node, etype: EventType, subtype: str | None, owner: str) -> dict[str, Any]:
        date_node = node.first("DATE")
        date = time = None
        utc = False
        date_text = None
        if date_node is not None:
            date_text = date_node.value
            date, warns = parse_date(date_node.value, date_node.val("PHRASE"))
            for w in warns:
                self.warn(date_node.line, "date", w)
            tnode = date_node.first("TIME")
            if tnode is not None:
                time, utc, twarns = parse_time(tnode.value)
                for w in twarns:
                    self.warn(tnode.line, "time", w)
        # 5.5.x also allowed TIME directly under the event in some exporters
        if time is None and node.first("TIME") is not None:
            time, utc, _ = parse_time(node.val("TIME"))
        plac = node.first("PLAC")
        place = _clip(plac.value, 500) if plac is not None else None
        lat = lon = None
        if plac is not None:
            mp = plac.first("MAP")
            if mp is not None:
                lat, lon = _coord(mp.val("LATI"), "NS"), _coord(mp.val("LONG"), "EW")
        if place is None and node.val("ADDR"):
            place = _clip(node.val("ADDR"), 500)
        if place:
            self.places.add(place.lower())
        type_val = _clip(node.val("TYPE"), 80)
        if node.tag == "EVEN":
            subtype = (type_val or "other").lower()[:80]
            as_type = subtype.replace(" ", "_")
            if as_type in {t.value for t in EventType} and as_type != EventType.OTHER.value:
                etype, subtype = EventType(as_type), None
        elif type_val and not subtype:
            subtype = type_val.lower()[:80]
        desc_parts: list[str] = []
        if node.value and node.value.strip().upper() != "Y":
            desc_parts.append(node.value.strip())
        for nn in node.all("NOTE") + node.all("SNOTE"):
            t = self._note_text(nn)
            if t:
                desc_parts.append(t)
        preserved = []
        birth_conf = None
        adop_famc = None
        for c in node.children:
            if c.tag in ("DATE", "PLAC", "TYPE", "NOTE", "SNOTE", "SOUR", "OBJE", "ADDR", "TIME"):
                continue
            if c.tag == "CAUS":
                continue
            if c.tag == "FAMC" and etype == EventType.ADOPTION:
                adop_famc = {"family": c.pointer, "by": (c.val("ADOP") or "BOTH").upper()}
                continue
            if c.tag.startswith("_"):
                d = ext.resolve(c.tag, self.schema)
                if d is not None and d.kind == ext.KIND_BIRTH_TIME and etype == EventType.BIRTH:
                    self.ext_used[d.tag] += 1
                    birth_conf = (c.value or "", c.line)
                    continue
                p = self._unhandled(c, node.tag, preserve=True)
                if p:
                    preserved.append(p)
                continue
            self._unhandled(c, node.tag, preserve=False)
        self._media(node)
        ev = {
            "tag": node.tag,
            "type": etype.value,
            "subtype": subtype,
            "date": date,
            "date_text": date_text,
            "time": time,
            "utc": utc,
            "place": place,
            "latitude": lat,
            "longitude": lon,
            "reason": _clip(node.val("CAUS"), MAX_TEXT),
            "description": _clip("\n\n".join(desc_parts), MAX_TEXT),
            "citations": self._citations(node),
            "preserved": preserved,
            "line": node.line,
        }
        if adop_famc and adop_famc["family"]:
            ev["adoption_family"] = adop_famc
        if birth_conf is not None:
            self._apply_birth_conf(ev, *birth_conf)
        return ev

    def _apply_birth_conf(self, ev: dict[str, Any], payload: str, line: int) -> None:
        tokens = payload.strip().lower().split()
        precision = tokens[0] if tokens else ""
        source = tokens[1] if len(tokens) > 1 else TimeSource.UNKNOWN.value
        if precision not in {p.value for p in TimePrecision} or source not in {s.value for s in TimeSource}:
            self.warn(line, "extension_value", f"_IND_BIRTH_TIME_CONF value {payload!r} is not recognised")
            return
        if not ev.get("time"):
            self.warn(line, "extension_context", "_IND_BIRTH_TIME_CONF without a birth TIME was ignored")
            return
        if not time_precision_valid(precision, source):
            self.warn(
                line,
                "extension_value",
                f"birth time precision {precision!r} is not valid with source {source!r}",
            )
            return
        ev["time"] = {**ev["time"], "precision": precision, "source": source}

    # ------------------------------------------------------------------ individuals
    def _stage_indi(self, r: Node, xref: str) -> dict[str, Any]:
        names = self._stage_names(r)
        if not names:
            self.warn(r.line, "no_name", f"{xref} has no name; recorded as 'Unnamed'")
            names = [
                {
                    "given": None,
                    "surname": None,
                    "prefix": None,
                    "suffix": None,
                    "full": "Unnamed",
                    "type": NameType.BIRTH.value,
                    "language": None,
                    "script": None,
                    "is_preferred": True,
                    "citations": [],
                    "line": r.line,
                }
            ]
        sex = None
        if r.val("SEX"):
            sex = SEX.get((r.val("SEX") or "").strip().upper()[:1])
            if sex is None:
                self.warn(r.line, "sex_value", f"Unrecognised SEX value {r.val('SEX')!r}")
        events: list[dict[str, Any]] = []
        famc: list[dict[str, Any]] = []
        fams: list[str] = []
        notes: list[str] = []
        resn: list[str] = []
        heritage: list[dict[str, Any]] = []
        astrology: dict[str, Any] = {}
        preserved: list[dict[str, Any]] = []
        birth_conf_nodes: list[Node] = []
        handled_simple = {"NAME", "SEX", "SOUR", "OBJE"}
        for c in r.children:
            tag = c.tag
            if tag in handled_simple:
                continue
            if tag in INDI_EVENTS:
                et, sub = INDI_EVENTS[tag]
                events.append(self._stage_event(c, et, sub, xref))
            elif tag in OTHER_INDI_EVENTS:
                events.append(self._stage_event(c, EventType.OTHER, tag.lower(), xref))
            elif tag == "EVEN":
                events.append(self._stage_event(c, EventType.OTHER, None, xref))
            elif tag == "FAMC":
                if c.pointer:
                    pedi = c.first("PEDI")
                    famc.append(
                        {
                            "family": c.pointer,
                            "pedi": (pedi.value or "").strip().upper() if pedi is not None else None,
                            "pedi_phrase": (pedi.val("PHRASE") or "").strip().lower() or None
                            if pedi is not None
                            else None,
                            "status": (c.val("STAT") or "").strip().upper() or None,
                        }
                    )
            elif tag == "FAMS":
                if c.pointer:
                    fams.append(c.pointer)
            elif tag in ("NOTE", "SNOTE"):
                t = self._note_text(c)
                if t:
                    notes.append(t)
            elif tag in STANDARD_ASSERTIONS:
                value = _clip(c.value, 2000)
                if value:
                    heritage.append(
                        {
                            "attribute": STANDARD_ASSERTIONS[tag],
                            "tag": tag,
                            "value": value,
                            "citations": self._citations(c),
                        }
                    )
                else:  # e.g. RELI with only a TYPE or DATE: keep it verbatim rather than guess
                    p = self._unhandled(c, "INDI", preserve=True)
                    if p:
                        preserved.append(p)
            elif tag == "RESN":
                resn += [x.strip().upper() for x in (c.value or "").split(",") if x.strip()]
            elif tag.startswith("_"):
                d = ext.resolve(tag, self.schema)
                if d is None or d.kind == ext.KIND_PRESERVED:
                    if d is not None:
                        self.ext_used[d.tag] += 1
                        self.preserved_count += 1
                        preserved.append(
                            {
                                "tag": d.tag,
                                "uri": d.uri,
                                "payload": "\n".join(
                                    node_lines(Node(0, d.tag, c.value, None, c.line, c.children))
                                ),
                                "line": c.line,
                            }
                        )
                    else:
                        p = self._unhandled(c, "INDI", preserve=True)
                        if p:
                            preserved.append(p)
                    continue
                self.ext_used[d.tag] += 1
                if d.kind == ext.KIND_ASSERTION:
                    value = _clip(c.value, 2000)
                    if not value:
                        self.warn(c.line, "extension_value", f"{tag} without a value was ignored")
                        continue
                    heritage.append(
                        {"attribute": d.target, "tag": d.tag, "value": value, "citations": self._citations(c)}
                    )
                elif d.kind == ext.KIND_ASTROLOGY:
                    self._stage_astrology(astrology, d, c)
                elif d.kind == ext.KIND_BIRTH_TIME:
                    birth_conf_nodes.append(c)
            elif tag in IGNORED_TAGS:
                continue
            else:
                p = self._unhandled(c, "INDI", preserve=True)
                if p:
                    preserved.append(p)
        self._media(r)
        # INDI-level _IND_BIRTH_TIME_CONF applies to the first birth event
        births = [e for e in events if e["type"] == EventType.BIRTH.value]
        for bc in birth_conf_nodes:
            if births:
                self._apply_birth_conf(births[0], bc.value or "", bc.line)
            else:
                self.warn(
                    bc.line, "extension_context", "_IND_BIRTH_TIME_CONF without a birth event was ignored"
                )
        occupation = next(
            (
                e["description"]
                for e in events
                if e["type"] == EventType.OCCUPATION.value and e["description"]
            ),
            None,
        )
        status, birth_year = self._status(events)
        preferred = next(n for n in names if n["is_preferred"])
        return {
            "xref": xref,
            "line": r.line,
            "display_name": _display(preferred),
            "names": names,
            "sex": sex,
            "events": events,
            "famc": famc,
            "fams": fams,
            "notes": notes,
            "resn": resn,
            "profile_status": status,
            "birth_year": birth_year,
            "heritage": heritage,
            "astrology": astrology or None,
            "preserved": preserved,
            "citations": self._citations(r),
            "occupation": _clip(occupation, 200),
            "media": self._media_list(r),
        }

    def _stage_astrology(self, astrology: dict[str, Any], d: ext.ExtensionDef, c: Node) -> None:
        value = _clip(c.value, 60)
        if not value:
            self.warn(c.line, "extension_value", f"{c.tag} without a value was ignored")
            return
        if d.target == "nakshatra_pada":
            if not value.isdigit() or not 1 <= int(value) <= 4:
                self.warn(c.line, "extension_value", f"{c.tag} must be 1-4, got {value!r}")
                return
            astrology["nakshatra_pada"] = int(value)
        elif d.target:
            if d.target in astrology and astrology[d.target] != value:
                self.warn(c.line, "extension_repeat", f"Repeated {c.tag}; only the first value is imported")
                return
            astrology[d.target] = value

    def _status(self, events: list[dict[str, Any]]) -> tuple[str, int | None]:
        death_types = {EventType.DEATH.value, EventType.BURIAL.value, EventType.CREMATION.value}
        birth_year: int | None = None
        for e in events:
            if e["type"] == EventType.BIRTH.value and e.get("date"):
                d = GenealogicalDate.model_validate(e["date"])
                lo, hi = d.sort_range()
                latest = hi or lo
                if latest is not None:
                    birth_year = latest.year
                    break
        if any(e["type"] in death_types for e in events):
            return "deceased", birth_year
        if birth_year is not None and self.today.year - birth_year < PRESUMED_LIVING_YEARS:
            return "living", birth_year
        return "unknown", birth_year

    # ------------------------------------------------------------------ families
    def _stage_fam(self, r: Node, xref: str) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        notes: list[str] = []
        preserved: list[dict[str, Any]] = []
        no_marr = False
        husb = r.first("HUSB")
        wife = r.first("WIFE")
        children = [c.pointer for c in r.all("CHIL") if c.pointer]
        for c in r.children:
            tag = c.tag
            if tag in ("HUSB", "WIFE", "CHIL", "SOUR", "OBJE"):
                continue
            if tag in FAM_EVENTS:
                et, sub = FAM_EVENTS[tag]
                events.append(self._stage_event(c, et, sub, xref))
            elif tag in OTHER_FAM_EVENTS:
                events.append(self._stage_event(c, EventType.OTHER, tag.lower(), xref))
            elif tag == "EVEN":
                events.append(self._stage_event(c, EventType.OTHER, None, xref))
            elif tag == "NO":
                if (c.value or "").strip().upper() == "MARR":
                    no_marr = True
            elif tag in ("NOTE", "SNOTE"):
                t = self._note_text(c)
                if t:
                    notes.append(t)
            elif tag in IGNORED_TAGS or tag in ("NCHI", "RESN"):
                continue
            else:
                p = self._unhandled(c, "FAM", preserve=True)
                if p:
                    preserved.append(p)
        self._media(r)
        tags = {e["tag"] for e in events}
        subtypes = {e["subtype"] for e in events if e["subtype"]}
        rtype = RelationshipType.SPOUSE
        if tags & {"DIV", "ANUL"}:
            rtype = RelationshipType.DIVORCED_SPOUSE
        elif subtypes & {"separation", "separated"}:
            rtype = RelationshipType.SEPARATED_SPOUSE
        elif no_marr and "MARR" not in tags:
            rtype = RelationshipType.PARTNER
        start = next((e["date"] for e in events if e["tag"] == "MARR" and e.get("date")), None)
        end = next((e["date"] for e in events if e["tag"] in ("DIV", "ANUL") and e.get("date")), None)
        return {
            "xref": xref,
            "line": r.line,
            "husb": husb.pointer if husb is not None else None,
            "wife": wife.pointer if wife is not None else None,
            "children": children,
            "events": events,
            "relationship_type": rtype.value,
            "start_date": start,
            "end_date": end,
            "citations": self._citations(r),
            "notes": notes,
            "preserved": preserved,
        }

    def _link_families(self, individuals: list[dict[str, Any]], families: list[dict[str, Any]]) -> None:
        """Reconcile FAM.HUSB/WIFE/CHIL with INDI.FAMS/FAMC (either side may be missing)."""
        indi_x = {i["xref"] for i in individuals}
        fam_by = {f["xref"]: f for f in families}
        for f in families:
            for role in ("husb", "wife"):
                if f[role] and f[role] not in indi_x:
                    self.warn(
                        f["line"], "dangling_pointer", f"{f['xref']} {role.upper()} {f[role]} is not defined"
                    )
                    f[role] = None
            kids = []
            for c in f["children"]:
                if c in indi_x:
                    kids.append(c)
                else:
                    self.warn(f["line"], "dangling_pointer", f"{f['xref']} CHIL {c} is not defined")
            f["children"] = kids
        for i in individuals:
            for fc in i["famc"]:
                fam = fam_by.get(fc["family"])
                if fam is None:
                    self.warn(
                        i["line"], "dangling_pointer", f"{i['xref']} FAMC {fc['family']} is not defined"
                    )
                    continue
                if i["xref"] not in fam["children"]:
                    fam["children"].append(i["xref"])
            for fx in i["fams"]:
                fam = fam_by.get(fx)
                if fam is None:
                    self.warn(i["line"], "dangling_pointer", f"{i['xref']} FAMS {fx} is not defined")
                    continue
                if i["xref"] in (fam["husb"], fam["wife"]):
                    continue
                if fam["husb"] is None and i["sex"] != "female":
                    fam["husb"] = i["xref"]
                elif fam["wife"] is None:
                    fam["wife"] = i["xref"]
                elif fam["husb"] is None:
                    fam["husb"] = i["xref"]
                else:
                    self.warn(
                        i["line"], "family_partners", f"{fx} already has two partners; {i['xref']} ignored"
                    )
            for e in i["events"]:
                af = e.get("adoption_family")
                if af and af["family"] not in fam_by:
                    self.warn(e["line"], "dangling_pointer", f"ADOP FAMC {af['family']} is not defined")


def _coord(v: str | None, dirs: str) -> float | None:
    if not v:
        return None
    m = re.match(r"^([NSEW])?\s*(-?\d+(?:\.\d+)?)$", v.strip().upper())
    if not m:
        return None
    num = float(m.group(2))
    if m.group(1) and m.group(1) == dirs[1]:
        num = -abs(num)
    limit = 90 if dirs == "NS" else 180
    return num if -limit <= num <= limit else None


def _display(n: dict[str, Any]) -> str:
    if n.get("given") or n.get("surname"):
        parts = [n.get("prefix"), n.get("given"), n.get("surname"), n.get("suffix")]
        return " ".join(p for p in parts if p)[:300]
    return (n.get("full") or "Unnamed")[:300]


def stage(result: ParseResult, today: dt.date | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    return Stager(result, today).run()


def _is_photo_container(r: Node) -> bool:
    """An INDI record that only holds media: no name, no family links, no events or facts.

    MyHeritage exports its "Unassociated photos" album this way (``_UID Unassociated photos``). Real
    people without a name still have a family link or an event, so they are kept.
    """
    if r.first("OBJE") is None or any(r.first(t) is not None for t in ("NAME", "FAMC", "FAMS")):
        return False
    if (r.val("_UID") or "").strip().lower() == "unassociated photos":
        return True
    if (r.val("SEX") or "U").strip().upper()[:1] != "U":
        return False
    return all(c.tag in _PHOTO_CONTAINER_TAGS for c in r.children)
