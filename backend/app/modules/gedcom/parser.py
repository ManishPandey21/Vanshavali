"""Tolerant GEDCOM line parser (5.5, 5.5.1 and 7.x).

The parser never raises on bad input. It decodes the bytes (BOM, ``HEAD.CHAR``, UTF-8 with a
latin-1 fallback), splits lines, builds a tree of :class:`Node` objects, folds ``CONT``/``CONC``
continuations into their parent payload and reports every problem as a :class:`Issue` with the
1-based line number. Callers enforce the byte cap before calling (``max_bytes`` is re-checked here);
``max_records`` caps the number of level-0 records.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass, field

DEFAULT_MAX_RECORDS = 250_000
MAX_LEVEL = 99

_LINE_RE = re.compile(r"^(\d{1,2}) (?:(@[^@ ]+@) )?([A-Za-z0-9_]+)(?: (.*))?$")
_LOOSE_LINE_RE = re.compile(r"^\s*(\d{1,2})\s+(?:(@[^@\s]+@)\s+)?([A-Za-z0-9_]+)(?:\s(.*))?$")
_POINTER_RE = re.compile(r"^@[^@#][^@]*@$")
_CHAR_RE = re.compile(rb"^\s*1\s+CHAR\s+([A-Za-z0-9_\-]+)", re.MULTILINE)


@dataclass
class Issue:
    line: int | None
    code: str
    message: str
    severity: str = "warning"  # warning | error

    def as_dict(self) -> dict[str, object]:
        return {"line": self.line, "code": self.code, "message": self.message, "severity": self.severity}


@dataclass
class Node:
    level: int
    tag: str
    value: str | None = None
    xref: str | None = None
    line: int = 0
    children: list[Node] = field(default_factory=list)

    # ---- navigation ----
    def first(self, tag: str) -> Node | None:
        return next((c for c in self.children if c.tag == tag), None)

    def all(self, tag: str) -> list[Node]:
        return [c for c in self.children if c.tag == tag]

    def val(self, tag: str) -> str | None:
        c = self.first(tag)
        return c.value if c is not None else None

    @property
    def pointer(self) -> str | None:
        """The xref this node points to (``@I1@``), or None if the payload is not a pointer."""
        v = self.value
        if v and _POINTER_RE.match(v) and v != "@VOID@":
            return v
        return None

    def walk(self) -> Iterator[Node]:
        yield self
        for c in self.children:
            yield from c.walk()


@dataclass
class ParseResult:
    records: list[Node]
    version: str | None  # "5.5" | "5.5.1" | "7.0" | raw value
    encoding: str
    issues: list[Issue]
    line_count: int
    truncated: bool = False

    @property
    def head(self) -> Node | None:
        return next((r for r in self.records if r.tag == "HEAD"), None)

    @property
    def is_v7(self) -> bool:
        return bool(self.version and self.version.startswith("7"))

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "warning"]


# --------------------------------------------------------------------------- ANSEL
# ANSEL (ANSI Z39.47) as used by GEDCOM 5.5.x: 0x00-0x7F ASCII, spacing specials, and combining
# diacritics that PRECEDE their base letter (Unicode puts them after).
_ANSEL_SPECIAL = {
    0xA1: "Ł", 0xA2: "Ø", 0xA3: "Đ", 0xA4: "Þ", 0xA5: "Æ", 0xA6: "Œ",
    0xA7: "ʹ", 0xA8: "·", 0xA9: "♭", 0xAA: "®", 0xAB: "±", 0xAC: "Ơ",
    0xAD: "Ư", 0xAE: "ʼ", 0xB0: "ʻ", 0xB1: "ł", 0xB2: "ø", 0xB3: "đ",
    0xB4: "þ", 0xB5: "æ", 0xB6: "œ", 0xB7: "ʺ", 0xB8: "ı", 0xB9: "£",
    0xBA: "ð", 0xBC: "ơ", 0xBD: "ư", 0xBE: "□", 0xBF: "■", 0xC0: "°",
    0xC1: "ℓ", 0xC2: "℗", 0xC3: "©", 0xC4: "♯", 0xC5: "¿", 0xC6: "¡",
    0xC7: "ß", 0xC8: "€", 0xCF: "ß",
}  # fmt: skip
_ANSEL_COMBINING = {
    0xE0: "̉", 0xE1: "̀", 0xE2: "́", 0xE3: "̂", 0xE4: "̃", 0xE5: "̄",
    0xE6: "̆", 0xE7: "̇", 0xE8: "̈", 0xE9: "̌", 0xEA: "̊", 0xEB: "︠",
    0xEC: "︡", 0xED: "̕", 0xEE: "̋", 0xEF: "̐", 0xF0: "̧", 0xF1: "̨",
    0xF2: "̣", 0xF3: "̤", 0xF4: "̥", 0xF5: "̳", 0xF6: "̲", 0xF7: "̦",
    0xF8: "̜", 0xF9: "̮", 0xFA: "︢", 0xFB: "︣", 0xFE: "̓",
}  # fmt: skip


def decode_ansel(data: bytes) -> tuple[str, int]:
    """Best-effort ANSEL → Unicode (NFC). Returns (text, number of unmappable bytes)."""
    out: list[str] = []
    pending: list[str] = []
    bad = 0
    for b in data:
        if b < 0x80:
            ch = chr(b)
            if ch in "\r\n":
                out.extend(pending)  # dangling diacritics at end of line: keep, don't lose data
                pending = []
                out.append(ch)
                continue
            out.append(ch)
            if pending:
                out.extend(pending)
                pending = []
        elif b in _ANSEL_COMBINING:
            pending.append(_ANSEL_COMBINING[b])
        elif b in _ANSEL_SPECIAL:
            out.append(_ANSEL_SPECIAL[b])
            if pending:
                out.extend(pending)
                pending = []
        else:
            bad += 1
            out.append("�")
    out.extend(pending)
    return unicodedata.normalize("NFC", "".join(out)), bad


# --------------------------------------------------------------------------- decoding
def _looks_utf16(data: bytes) -> str | None:
    sample = data[:200]
    if len(sample) < 4:
        return None
    even_nuls = sum(1 for i in range(0, len(sample), 2) if sample[i] == 0)
    odd_nuls = sum(1 for i in range(1, len(sample), 2) if sample[i] == 0)
    half = len(sample) // 2
    if odd_nuls > half * 0.6:
        return "utf-16-le"
    if even_nuls > half * 0.6:
        return "utf-16-be"
    return None


def _decode_utf8_or_latin1(data: bytes, issues: list[Issue], declared: str) -> tuple[str, str]:
    try:
        return data.decode("utf-8"), "UTF-8"
    except UnicodeDecodeError as exc:
        line = data[: exc.start].count(b"\n") + 1
        issues.append(
            Issue(
                line,
                "encoding_fallback",
                f"File is not valid UTF-8 (declared {declared}); decoded as latin-1. "
                "Check non-English characters.",
            )
        )
        return data.decode("latin-1"), "LATIN-1"


def decode_bytes(data: bytes) -> tuple[str, str, list[Issue]]:
    """Detect the encoding and decode. Returns (text, encoding label, issues)."""
    issues: list[Issue] = []
    if data.startswith(b"\xef\xbb\xbf"):
        text, enc = _decode_utf8_or_latin1(data[3:], issues, "UTF-8 BOM")
        return text, enc, issues
    if data.startswith(b"\xff\xfe"):
        return data[2:].decode("utf-16-le", errors="replace"), "UTF-16LE", issues
    if data.startswith(b"\xfe\xff"):
        return data[2:].decode("utf-16-be", errors="replace"), "UTF-16BE", issues
    u16 = _looks_utf16(data)
    if u16:
        issues.append(Issue(None, "encoding_no_bom", "UTF-16 file without a byte-order mark"))
        return data.decode(u16, errors="replace"), u16.upper().replace("-", ""), issues
    m = _CHAR_RE.search(data[:4096])
    declared = m.group(1).decode("ascii", "replace").upper() if m else None
    if declared == "ANSEL":
        text, bad = decode_ansel(data)
        issues.append(
            Issue(
                None,
                "encoding_ansel",
                "ANSEL-encoded file decoded best-effort; verify names with diacritics",
            )
        )
        if bad:
            issues.append(Issue(None, "encoding_ansel_unmapped", f"{bad} ANSEL byte(s) could not be mapped"))
        return text, "ANSEL", issues
    if declared in ("ANSI", "WINDOWS-1252", "CP1252", "IBMPC", "IBM_WINDOWS"):
        issues.append(
            Issue(
                None, "encoding_legacy", f"Legacy {declared} encoding decoded as Windows-1252; verify names"
            )
        )
        try:
            return data.decode("cp1252"), "CP1252", issues
        except UnicodeDecodeError:
            return data.decode("latin-1"), "LATIN-1", issues
    if declared in ("LATIN1", "ISO-8859-1", "ISO8859-1"):
        return data.decode("latin-1"), "LATIN-1", issues
    if declared == "UNICODE":
        issues.append(Issue(None, "encoding_unicode_no_bom", "CHAR UNICODE without a BOM; trying UTF-8"))
    text, enc = _decode_utf8_or_latin1(data, issues, declared or "UTF-8")
    return text, enc, issues


# --------------------------------------------------------------------------- parsing
def _normalise_version(raw: str | None) -> str | None:
    if not raw:
        return None
    v = raw.strip()
    if v.startswith("7"):
        return "7.0"
    if v.startswith("5.5.1"):
        return "5.5.1"
    if v.startswith("5.5.5"):
        return "5.5.5"
    if v.startswith("5.5"):
        return "5.5"
    return v[:20]


def _unescape(value: str, v7: bool) -> str:
    if value.startswith("@@"):
        return value[1:]
    if not v7 and "@@" in value:
        return value.replace("@@", "@")
    return value


def looks_like_gedcom(data: bytes) -> bool:
    head = data[:512]
    for bom in (b"\xef\xbb\xbf",):
        if head.startswith(bom):
            head = head[len(bom) :]
    if head.startswith((b"\xff\xfe", b"\xfe\xff")) or _looks_utf16(head):
        try:
            enc = "utf-16" if head[:2] in (b"\xff\xfe", b"\xfe\xff") else _looks_utf16(head) or "utf-16"
            head = data[:512].decode(enc, errors="ignore").encode("utf-8")
        except (LookupError, UnicodeError):
            return False
        head = head.lstrip("﻿".encode())
    return re.match(rb"^\s*0\s+HEAD\b", head) is not None


def parse(
    data: bytes, *, max_bytes: int | None = None, max_records: int = DEFAULT_MAX_RECORDS
) -> ParseResult:
    if max_bytes is not None and len(data) > max_bytes:
        return ParseResult(
            [], None, "unknown", [Issue(None, "file_too_large", "File exceeds the size limit", "error")], 0
        )
    text, encoding, issues = decode_bytes(data)
    text = text.lstrip("﻿")
    lines = re.split(r"\r\n|\r|\n", text)
    # detect version early so payload unescaping and CONC checks follow the right rules
    version: str | None = None
    for i, ln in enumerate(lines[:400]):
        m = _LOOSE_LINE_RE.match(ln)
        if m and m.group(1) == "2" and m.group(3) == "VERS" and i > 0:
            # HEAD.GEDC.VERS: look back for "1 GEDC"
            for back in range(i - 1, max(-1, i - 5), -1):
                mb = _LOOSE_LINE_RE.match(lines[back])
                if mb and mb.group(1) == "1":
                    if mb.group(3) == "GEDC":
                        version = _normalise_version(m.group(4))
                    break
            if version:
                break
        if m and m.group(1) == "0" and m.group(3) not in ("HEAD",) and i > 0:
            break
    v7 = bool(version and version.startswith("7"))
    if version is None:
        issues.append(
            Issue(None, "version_missing", "HEAD.GEDC.VERS is missing; assuming GEDCOM 5.5.1 rules")
        )
    elif version not in ("5.5", "5.5.1", "5.5.5", "7.0"):
        issues.append(Issue(None, "version_unknown", f"Unrecognised GEDCOM version {version!r}"))

    records: list[Node] = []
    stack: list[Node] = []
    truncated = False
    conc_in_v7 = 0
    loose_lines = 0
    for idx, raw in enumerate(lines, start=1):
        if raw.strip() == "":
            continue
        m = _LINE_RE.match(raw)
        if m is None:
            m = _LOOSE_LINE_RE.match(raw)
            if m is not None:
                loose_lines += 1
        if m is None:
            issues.append(Issue(idx, "syntax", f"Unparseable line: {raw[:80]!r}", "error"))
            continue
        level = int(m.group(1))
        xref = m.group(2)
        tag = m.group(3).upper()
        value = m.group(4)
        if value is not None:
            value = _unescape(value, v7)
        if level == 0:
            if len(records) >= max_records:
                issues.append(
                    Issue(
                        idx,
                        "too_many_records",
                        f"More than {max_records} records; the rest was ignored",
                        "error",
                    )
                )
                truncated = True
                break
            node = Node(0, tag, value if value != "" else None, xref, idx)
            records.append(node)
            stack = [node]
            continue
        if not stack:
            issues.append(Issue(idx, "orphan_line", "Line appears before any level-0 record", "error"))
            continue
        parent_level = stack[-1].level
        if level > parent_level + 1:
            issues.append(
                Issue(
                    idx,
                    "level_jump",
                    f"Level jumps from {parent_level} to {level}; attached to the previous line",
                    "error",
                )
            )
            level = parent_level + 1
        while stack and stack[-1].level >= level:
            stack.pop()
        if not stack:
            issues.append(Issue(idx, "orphan_line", "Line has no parent record", "error"))
            continue
        parent = stack[-1]
        if tag in ("CONT", "CONC"):
            if tag == "CONC" and v7:
                conc_in_v7 += 1
            addition = value or ""
            if tag == "CONT":
                parent.value = (parent.value or "") + "\n" + addition
            else:
                parent.value = (parent.value or "") + addition
            continue
        node = Node(level, tag, value if value != "" else None, xref, idx)
        parent.children.append(node)
        stack.append(node)
    if conc_in_v7:
        issues.append(
            Issue(
                None, "conc_in_v7", f"{conc_in_v7} CONC line(s) are not allowed in GEDCOM 7; they were joined"
            )
        )
    if loose_lines:
        issues.append(
            Issue(None, "loose_whitespace", f"{loose_lines} line(s) used non-standard whitespace; accepted")
        )
    if not records or records[0].tag != "HEAD":
        issues.append(Issue(1, "missing_head", "The file does not start with a HEAD record", "error"))
    if not truncated and (not records or records[-1].tag != "TRLR"):
        issues.append(Issue(len(lines), "missing_trlr", "The file does not end with a TRLR record"))
    return ParseResult(records, version, encoding, issues, len(lines), truncated)


def head_schema(result: ParseResult) -> dict[str, str]:
    """``HEAD.SCHMA.TAG`` → {extension tag: URI} (GEDCOM 7)."""
    out: dict[str, str] = {}
    head = result.head
    if head is None:
        return out
    schma = head.first("SCHMA")
    if schma is None:
        return out
    for t in schma.all("TAG"):
        parts = (t.value or "").split(None, 1)
        if len(parts) == 2 and parts[0].startswith("_"):
            out[parts[0].upper()] = parts[1].strip()
    return out


def head_char(result: ParseResult) -> str | None:
    head = result.head
    return head.val("CHAR") if head is not None else None


# --------------------------------------------------------------------------- writing
_XREF_TOKEN = re.compile(r"^@[^@]+@$")


def node_lines(node: Node, base_level: int = 0) -> list[str]:
    """Serialise a node subtree (GEDCOM 7 rules: CONT for line breaks, leading '@' escaped)."""
    out: list[str] = []
    _emit(node, base_level, out)
    return out


def format_line(level: int, tag: str, value: str | None = None, xref: str | None = None) -> list[str]:
    head = f"{level} {xref + ' ' if xref else ''}{tag}"
    if value is None or value == "":
        return [head]
    parts = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out = [f"{head} {_escape(parts[0])}" if parts[0] != "" else head]
    for p in parts[1:]:
        out.append(f"{level + 1} CONT {_escape(p)}" if p != "" else f"{level + 1} CONT")
    return out


def _escape(v: str) -> str:
    if v.startswith("@") and not _XREF_TOKEN.match(v):
        return "@" + v
    return v


def _emit(node: Node, level: int, out: list[str]) -> None:
    out.extend(format_line(level, node.tag, node.value, node.xref))
    for c in node.children:
        _emit(c, level + 1, out)
