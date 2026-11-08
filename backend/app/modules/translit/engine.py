"""Name transliteration suggestions, Hindi Devanagari <-> Latin (ADR-0025).

Local and deterministic: a reviewed lexicon of common names first, Hindi rules on top of
``indic-transliteration`` second. The engine only *suggests*: callers never write its output
anywhere without a user's explicit choice, and it never learns from what families type.

Latin -> Devanagari rules (for tokens not in the lexicon), on the lower-cased token:
* casual spellings are mapped to ITRANS (aa -> A, ee -> I, oo -> U, x -> kSh, w -> v);
* a word-final "a" is long (Sharma -> शर्मा); a word-final "i" is long (Lakshmi -> लक्ष्मी);
* the word-final halant the library leaves is dropped (Ramesh -> रमेश);
* vowel length inside a word is ambiguous, so the last short medial i and the first short medial a
  also yield the long alternatives (Vinita -> विनिता, विनीता; Rajesh -> रजेश, राजेश).

Devanagari -> Latin rules: syllables are read from the Devanagari, then the Hindi inherent vowel
(schwa) is dropped at the end of a word unless it follows a conjunct (रमेश -> Ramesh, but कृष्ण ->
Krishna), and in the medial V-C-a-C-V context, scanning from the right with no two adjacent
deletions (कमला -> Kamla). A word-initial आ is "Aa" (आरव -> Aarav); other long vowels fold to one
letter, with "ee"/"oo" offered as an alternative for a medial ई/ऊ (गीता -> Gita, Geeta).
"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

from indic_transliteration import sanscript
from indic_transliteration.sanscript import transliterate

ENGINE = "vanshavali-translit"
VERSION = "hi-Latn/1"
MAX_CANDIDATES = 3
MAX_TEXT = 200

Script = Literal["Deva", "Latn"]
Method = Literal["lexicon", "rules"]

_LEXICON_PATH = Path(__file__).parent / "lexicon" / "hi.json"
_DEVA = re.compile(r"[ऀ-ॿ]")
_LATIN = re.compile(r"[A-Za-z]")
_TOKEN = re.compile(r"[ऀ-ॿ]+|[A-Za-z]+(?:['’][A-Za-z]+)?")


@dataclass(frozen=True)
class Candidate:
    text: str
    method: Method


@dataclass(frozen=True)
class Lexicon:
    version: str
    to_deva: dict[str, tuple[str, ...]]  # lower-cased Latin spelling -> Devanagari forms
    to_latin: dict[str, tuple[str, ...]]  # Devanagari -> Latin spellings, preferred first


@lru_cache(maxsize=1)
def lexicon() -> Lexicon:
    raw = json.loads(_LEXICON_PATH.read_text(encoding="utf-8"))
    to_deva: dict[str, list[str]] = {}
    to_latin: dict[str, list[str]] = {}
    for e in raw["entries"]:
        deva = unicodedata.normalize("NFC", e["deva"])
        for latin in e["latin"]:
            forms = to_deva.setdefault(latin.lower(), [])
            if deva not in forms:
                forms.append(deva)
            spellings = to_latin.setdefault(deva, [])
            if latin not in spellings:
                spellings.append(latin)
    return Lexicon(
        version=str(raw["version"]),
        to_deva={k: tuple(v) for k, v in to_deva.items()},
        to_latin={k: tuple(v) for k, v in to_latin.items()},
    )


def script_of(text: str) -> Script | None:
    """Deva if the text has Devanagari, Latn if it has Latin letters only, else None."""
    if _DEVA.search(text):
        return "Deva"
    if _LATIN.search(text):
        return "Latn"
    return None


# ------------------------------------------------------------------ Latin -> Devanagari
_LATIN_TO_ITRANS = [
    ("ksh", "kSh"),
    ("aa", "A"),
    ("ee", "I"),
    ("oo", "U"),
    ("x", "kSh"),
    ("w", "v"),
    ("q", "k"),
]
_HALANT = "्"


def _latin_token_to_deva(token: str) -> list[str]:
    t = token.lower().replace("'", "").replace("’", "")
    for a, b in _LATIN_TO_ITRANS:
        t = t.replace(a, b)
    if t.endswith("a") and len(t) > 1:
        t = t[:-1] + "A"
    elif t.endswith("i") and len(t) > 1:
        t = t[:-1] + "I"
    variants = [t]
    # vowel length is not written in casual spellings: offer the long form of the last short
    # medial i (Sunita -> सुनीता, Vinita -> विनीता) and of the first short medial a
    # (Rajesh -> राजेश)
    for short, long, pick in (("i", "I", -1), ("a", "A", 0)):
        hits = list(re.finditer(rf"(?<=[^aeiouAIU]){short}(?=[^aeiouAIU])", t))
        if hits:
            m = hits[pick]
            variants.append(t[: m.start()] + long + t[m.end() :])
    out: list[str] = []
    for v in variants:
        d = transliterate(v, sanscript.ITRANS, sanscript.DEVANAGARI)
        if d.endswith(_HALANT):
            d = d[:-1]
        d = unicodedata.normalize("NFC", d)
        if d not in out:
            out.append(d)
    return out


# ------------------------------------------------------------------ Devanagari -> Latin
_CONSONANTS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh", "स": "s", "ह": "h",
    "क़": "q", "ख़": "kh", "ग़": "g", "ज़": "z", "ड़": "d", "ढ़": "rh", "फ़": "f", "य़": "y",
}  # fmt: skip
_NUKTA = "़"
_INDEPENDENT = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
}  # fmt: skip
_MATRAS = {
    "ा": "aa", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "ृ": "ri",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au",
}  # fmt: skip
_MARKS = {"ं": "n", "ँ": "n", "ः": "h"}


@dataclass
class _Syl:
    onset: list[str]  # Latin consonants of the onset cluster
    vowel: str  # "a" (inherent), "", or the vowel's long-form spelling
    inherent: bool = False
    initial: bool = False
    coda: str = ""  # anusvara/visarga


def _syllables(word: str) -> list[_Syl]:
    sylls: list[_Syl] = []
    cluster: list[str] = []
    chars = list(unicodedata.normalize("NFC", word))
    i = 0
    while i < len(chars):
        ch = chars[i]
        if i + 1 < len(chars) and chars[i + 1] == _NUKTA:
            ch = unicodedata.normalize("NFC", ch + _NUKTA)
            i += 1
        if ch in _CONSONANTS:
            cluster.append(_CONSONANTS[ch])
            nxt = chars[i + 1] if i + 1 < len(chars) else ""
            if nxt == _HALANT:
                i += 2
                continue
            if nxt in _MATRAS:
                sylls.append(_Syl(cluster, _MATRAS[nxt]))
                i += 2
            else:
                sylls.append(_Syl(cluster, "a", inherent=True))
                i += 1
            cluster = []
            continue
        if ch in _INDEPENDENT:
            sylls.append(_Syl([], _INDEPENDENT[ch], initial=not sylls))
        elif ch in _MARKS and sylls:
            sylls[-1].coda += _MARKS[ch]
        i += 1
    if cluster:  # a trailing halant: the consonants close the word with no vowel
        sylls.append(_Syl(cluster, ""))
    return sylls


def _delete_schwas(sylls: list[_Syl], medial: bool) -> list[_Syl]:
    out = [_Syl(list(s.onset), s.vowel, s.inherent, s.initial, s.coda) for s in sylls]
    last = out[-1] if out else None
    if last and last.inherent and len(out) > 1 and len(last.onset) == 1 and not last.coda:
        last.vowel = ""  # final schwa, unless after a conjunct (Krishna, Mishra)
    if medial:
        i = len(out) - 2
        while i > 0:
            s, prev, nxt = out[i], out[i - 1], out[i + 1]
            if (
                s.inherent
                and s.vowel
                and not s.coda
                and len(s.onset) == 1
                and prev.vowel
                and nxt.vowel
                and nxt.onset
            ):
                s.vowel = ""
                i -= 2  # never two adjacent deletions
            else:
                i -= 1
    return out


def _render(sylls: list[_Syl], long_medial: bool) -> str:
    parts: list[str] = []
    for idx, s in enumerate(sylls):
        v = s.vowel
        if v == "aa":
            v = "aa" if (s.initial and idx == 0) else "a"
        elif v in ("ee", "oo"):
            final = idx == len(sylls) - 1
            if final or not long_medial:
                v = "i" if v == "ee" else "u"
        parts.append("".join(s.onset) + v + s.coda)
    word = "".join(parts)
    return word[:1].upper() + word[1:]


def _deva_token_to_latin(token: str) -> list[str]:
    sylls = _syllables(token)
    if not sylls:
        return []
    out: list[str] = []
    for medial, long_medial in ((True, False), (True, True), (False, False)):
        w = _render(_delete_schwas(sylls, medial), long_medial)
        if w and w not in out:
            out.append(w)
    return out


# ------------------------------------------------------------------ public API
def suggest(text: str, target: Script) -> list[Candidate]:
    """At most MAX_CANDIDATES suggestions for ``text`` in the ``target`` script, lexicon first.

    Returns [] when the text is empty, too long, already in the target script, or has no letters
    of the other script: an honest "no suggestion" rather than a guess.
    """
    text = unicodedata.normalize("NFC", (text or "").strip())
    if not text or len(text) > MAX_TEXT:
        return []
    # suggest only when there is something in the other script to transliterate
    other = _LATIN if target == "Deva" else _DEVA
    if not other.search(text):
        return []
    tokens = _TOKEN.findall(text)
    if not tokens:
        return []
    lex = lexicon()
    options: list[list[str]] = []
    all_lexicon = True
    for tok in tokens:
        if target == "Deva":
            if not _LATIN.search(tok):
                options.append([tok])
                continue
            hit = lex.to_deva.get(tok.lower())
            opts = list(hit) if hit else _latin_token_to_deva(tok)
        else:
            if not _DEVA.search(tok):
                options.append([tok])
                continue
            hit = lex.to_latin.get(tok)
            opts = list(hit) if hit else _deva_token_to_latin(tok)
        if not hit:
            all_lexicon = False
        options.append(opts or [tok])
    method: Method = "lexicon" if all_lexicon else "rules"
    seen: list[str] = []
    for k in range(MAX_CANDIDATES):
        cand = " ".join(o[min(k, len(o) - 1)] for o in options)
        if cand not in seen:
            seen.append(cand)
    return [Candidate(c, method) for c in seen[:MAX_CANDIDATES]]
