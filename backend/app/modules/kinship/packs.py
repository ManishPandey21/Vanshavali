"""Regional kinship packs (ADR-0026 §6): code-reviewed JSON, one per language and region.

A pack maps a relationship chain pattern (``father.brother``) to the word families use. It is data,
not code: each pack names its reviewer, review date, source and licence. The resolver reads it; it
never sets anything about a person.

Visibility:
* ``reviewed`` packs are shown to every family;
* a ``draft`` pack marked ``in_use`` holds words families already saw before packs existed (the
  Hindi words of R1-R3); it stays visible, each word labelled "not yet reviewed", until its review;
* any other ``draft`` pack is visible only to reviewers (system administrators).
"""

from __future__ import annotations

import functools
import json
import re
from pathlib import Path
from typing import Any

PACK_DIR = Path(__file__).parent / "packs"
PATTERN = re.compile(r"^[a-z_]+(\.[a-z_]+){0,5}$")
CHAIN_WORDS = frozenset(
    {
        "father",
        "mother",
        "parent",
        "son",
        "daughter",
        "child",
        "brother",
        "sister",
        "sibling",
        "husband",
        "wife",
        "spouse",
    }
)
_KEY = re.compile(r"^kinship-[a-z]{2,3}(-[a-z]+)?$")
_STATUSES = {"draft", "reviewed"}


class KinshipPackError(ValueError):
    pass


def _check_entry(name: str, key: str, e: Any, where: str) -> None:
    if not isinstance(e, dict) or not str(e.get("term", "")).strip():
        raise KinshipPackError(f"{name}: {where} {key} has no term")
    if not str(e.get("transliteration", "")).strip():
        raise KinshipPackError(f"{name}: {where} {key} has no transliteration")


def validate(pack: dict[str, Any], name: str = "pack") -> None:
    for k in ("key", "lang", "region", "name", "status", "source", "licence", "words", "terms", "joiner"):
        if k not in pack:
            raise KinshipPackError(f"{name}: missing {k}")
    if not _KEY.match(pack["key"]):
        raise KinshipPackError(f"{name}: bad key {pack['key']!r}")
    if pack["status"] not in _STATUSES:
        raise KinshipPackError(f"{name}: bad status")
    if pack["status"] == "reviewed" and not (pack.get("reviewer") and pack.get("reviewed_on")):
        raise KinshipPackError(f"{name}: a reviewed pack names its reviewer and review date")
    if not {"en", "hi"} <= set(pack["name"]):
        raise KinshipPackError(f"{name}: name needs en and hi")
    for key in ("joiner", "joiner_feminine"):
        j = pack.get(key)
        if j is not None and ("{acc}" not in j or "{word}" not in j):
            raise KinshipPackError(f"{name}: {key} needs {{acc}} and {{word}}")
    if not set(pack.get("feminine_words", [])) <= CHAIN_WORDS:
        raise KinshipPackError(f"{name}: unknown feminine word")
    for w in pack["words"]:
        if w not in CHAIN_WORDS:
            raise KinshipPackError(f"{name}: unknown chain word {w}")
    for pattern, e in pack["terms"].items():
        words = pattern.split(".")
        if not PATTERN.match(pattern) or not set(words) <= CHAIN_WORDS:
            raise KinshipPackError(f"{name}: bad pattern {pattern!r}")
        _check_entry(name, pattern, e, "term")
        age = e.get("age")
        if age is not None:
            idx = age.get("index")
            if (
                not isinstance(idx, int)
                or not 0 <= idx < len(words)
                or words[idx] not in {"brother", "sister"}
            ):
                raise KinshipPackError(f"{name}: {pattern} age index must point at a sibling word")
            for order in ("elder", "younger"):
                _check_entry(name, pattern, age.get(order), f"age.{order} of")
        for sex, se in (e.get("speaker") or {}).items():
            if sex not in {"male", "female"}:
                raise KinshipPackError(f"{name}: {pattern} speaker must be male or female")
            _check_entry(name, pattern, se, f"speaker.{sex} of")


@functools.cache
def all_packs() -> tuple[dict[str, Any], ...]:
    packs = []
    for path in sorted(PACK_DIR.glob("*.json")):
        pack = json.loads(path.read_text(encoding="utf-8"))
        validate(pack, path.name)
        if pack["key"] != path.stem:
            raise KinshipPackError(f"{path.name}: key does not match the file name")
        packs.append(pack)
    return tuple(packs)


def review_status(pack: dict[str, Any]) -> str:
    return "reviewed" if pack["status"] == "reviewed" else "unreviewed"


def visible(pack: dict[str, Any], reviewer: bool) -> bool:
    return pack["status"] == "reviewed" or bool(pack.get("in_use")) or reviewer


def visible_packs(reviewer: bool) -> list[dict[str, Any]]:
    return [p for p in all_packs() if visible(p, reviewer)]


def choose(lang: str | None, region: str | None, reviewer: bool) -> dict[str, Any] | None:
    """The pack for a language (and region when given); reviewed packs first. English has none:
    the API's English label is the English word."""
    if not lang or lang == "en":
        return None
    candidates = [p for p in visible_packs(reviewer) if p["lang"] == lang]
    if region:
        exact = [p for p in candidates if p["region"] == region]
        candidates = exact or candidates
    candidates.sort(key=lambda p: (p["status"] != "reviewed", p["key"]))
    return candidates[0] if candidates else None
