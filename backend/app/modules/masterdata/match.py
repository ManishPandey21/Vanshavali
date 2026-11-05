"""Script- and spelling-tolerant matching for vocabulary search (ADR-0018 §5).

``search_key`` (person search) already folds case, accents and Devanagari → Latin. Vocabulary terms
are short single words written many ways (भरद्वाज / Bharadwaja / Bhardwaj, शाण्डिल्य / Sandilya),
so a looser key also drops inherent vowels and folds common romanisation pairs. Used only to
*find* suggestions — never to decide that two values are the same fact.
"""

from __future__ import annotations

import re

from app.core.textnorm import search_key

_FOLDS = (
    ("sh", "s"),
    ("w", "v"),
    ("th", "t"),
    ("dh", "d"),
    ("kh", "k"),
    ("gh", "g"),
    ("ph", "f"),
    ("bh", "b"),
    ("ee", "i"),
    ("oo", "u"),
)


def loose_key(text: str) -> str:
    k = search_key(text)
    for a, b in _FOLDS:
        k = k.replace(a, b)
    k = re.sub(r"[^a-z0-9 ]", "", k)
    k = re.sub(r"[aeiou]", "", k)  # inherent and long vowels vary most between spellings
    return re.sub(r"(.)\1+", r"\1", k).strip()


def keys_for(*texts: str | None) -> tuple[set[str], set[str]]:
    """(strict keys, loose keys) for every non-empty text."""
    strict = {search_key(t) for t in texts if t}
    loose = {loose_key(t) for t in texts if t}
    return {s for s in strict if s}, {s for s in loose if s}


def matches(query: str, strict: set[str], loose: set[str]) -> bool:
    """Prefix/word match on the strict key, or prefix match on the loose key."""
    q = search_key(query)
    if not q:
        return True
    if any(s.startswith(q) or f" {q}" in s for s in strict):
        return True
    lq = loose_key(query)
    return bool(lq) and any(s.startswith(lq) for s in loose)


def same_value(a: str, b: str) -> bool:
    """Whether two labels are the same entry written differently (used to avoid duplicates)."""
    return bool(a.strip()) and (
        search_key(a) == search_key(b) or (loose_key(a) == loose_key(b) and len(loose_key(a)) >= 3)
    )
