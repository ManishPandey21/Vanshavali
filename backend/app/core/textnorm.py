"""Search normalisation for multilingual Indian names (ADR-0007).

``search_key`` → lowercase ASCII romanisation (Indic scripts transliterated). ``phonetic_key`` →
metaphone per token. Stored alongside the original text, which is never modified.
"""

from __future__ import annotations

import re
import unicodedata

import jellyfish
from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

_SCRIPT_RANGES: list[tuple[int, int, str]] = [
    (0x0900, 0x097F, sanscript.DEVANAGARI),
    (0x0980, 0x09FF, sanscript.BENGALI),
    (0x0A00, 0x0A7F, sanscript.GURMUKHI),
    (0x0A80, 0x0AFF, sanscript.GUJARATI),
    (0x0B00, 0x0B7F, sanscript.ORIYA),
    (0x0B80, 0x0BFF, sanscript.TAMIL),
    (0x0C00, 0x0C7F, sanscript.TELUGU),
    (0x0C80, 0x0CFF, sanscript.KANNADA),
    (0x0D00, 0x0D7F, sanscript.MALAYALAM),
]

SCRIPT_CODES = {
    sanscript.DEVANAGARI: "Deva",
    sanscript.BENGALI: "Beng",
    sanscript.GURMUKHI: "Guru",
    sanscript.GUJARATI: "Gujr",
    sanscript.ORIYA: "Orya",
    sanscript.TAMIL: "Taml",
    sanscript.TELUGU: "Telu",
    sanscript.KANNADA: "Knda",
    sanscript.MALAYALAM: "Mlym",
}

# Tamil ச is usually romanised "s"/"ch"; the library maps it oddly, so route it via grantha ஸ.
_TAMIL_FIXES = str.maketrans({"ச": "ஸ"})

_ITRANS_FOLDS = [
    ("RRi", "ri"),
    ("RRI", "ri"),
    ("LLi", "li"),
    ("~n", "n"),
    ("~N", "n"),
    (".n", "n"),
    (".m", "m"),
    ("M", "n"),
    ("H", "h"),
    (".h", ""),
    ("^", ""),
    ("Sh", "sh"),
    ("shh", "sh"),
    ("chh", "chh"),
    ("Ch", "chh"),
    ("A", "a"),
    ("I", "i"),
    ("U", "u"),
    ("E", "e"),
    ("O", "o"),
]


def _script_of(ch: str) -> str | None:
    cp = ord(ch)
    for lo, hi, scheme in _SCRIPT_RANGES:
        if lo <= cp <= hi:
            return scheme
    return None


def detect_script(text: str) -> str | None:
    for ch in text:
        s = _script_of(ch)
        if s:
            return SCRIPT_CODES[s]
    if any(ch.isalpha() and ord(ch) < 0x250 for ch in text):
        return "Latn"
    if any(0x0600 <= ord(ch) <= 0x06FF for ch in text):
        return "Arab"
    return None


def romanize(text: str) -> str:
    """Transliterate Indic runs to ITRANS, then fold to plain lowercase ASCII."""
    text = unicodedata.normalize("NFKC", text or "")
    out: list[str] = []
    run: list[str] = []
    run_script: str | None = None

    def flush() -> None:
        nonlocal run, run_script
        if run:
            chunk = "".join(run)
            if run_script:
                if run_script == sanscript.TAMIL:
                    chunk = chunk.translate(_TAMIL_FIXES)
                chunk = transliterate(chunk, run_script, sanscript.ITRANS)
                for a, b in _ITRANS_FOLDS:
                    chunk = chunk.replace(a, b)
            out.append(chunk)
        run, run_script = [], None

    for ch in text:
        s = _script_of(ch)
        if s != run_script and run:
            flush()
        run_script = s if run == [] else run_script
        run.append(ch)
    flush()
    joined = "".join(out)
    # strip accents (IAST etc.), lowercase, keep alnum + spaces
    joined = "".join(c for c in unicodedata.normalize("NFKD", joined) if not unicodedata.combining(c))
    joined = re.sub(r"[^0-9a-zA-Z]+", " ", joined).lower()
    # collapse doubled vowels produced by ITRANS long vowels (aa, ii, uu, ee, oo)
    joined = re.sub(r"([aiueo])\1+", r"\1", joined)
    return re.sub(r"\s+", " ", joined).strip()


def phonetic_key(text: str) -> str:
    tokens = romanize(text).split()
    return " ".join(k for k in (jellyfish.metaphone(t) for t in tokens) if k)


def search_key(*parts: str | None) -> str:
    return " ".join(romanize(p) for p in parts if p).strip()
