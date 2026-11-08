"""Choose a kinship word for a relationship chain from a pack (ADR-0026 §6, ADR-0020 §5).

The word is chosen *from* what is recorded: the chain's words (which already carry each hop's sex,
or a neutral word when it is unknown or hidden), the age orders the API computed, and the viewer's
own sex for words that depend on the speaker. A chain the pack does not know gets no word (the
caller shows the English description), never a guess or another language's word. Where the word
depends on an age order that is not known, both words are given.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

Order = Literal["elder", "younger", "unknown"]
Basis = Literal["family_confirmed", "birth_dates", "unknown"]


@dataclass(frozen=True)
class Age:
    chain_index: int
    order: Order
    basis: Basis


@dataclass
class Resolved:
    pattern: str
    term: str
    transliteration: str
    alternatives: list[str] = field(default_factory=list)
    basis: Basis | None = None  # how the age-dependent part was decided; None when it does not apply
    age_order: Order | None = None


def pattern_of(chain: Sequence[str]) -> str:
    return ".".join(chain)


def resolve(
    pack: dict[str, Any], chain: Sequence[str], ages: Sequence[Age], speaker_sex: str | None = None
) -> Resolved | None:
    if not chain:
        return None
    pattern = pattern_of(chain)
    entry = pack["terms"].get(pattern)
    if entry is None:
        return None
    speaker = entry.get("speaker") or {}
    if speaker:
        if speaker_sex in speaker:
            entry = {**entry, **speaker[speaker_sex]}
        else:  # the viewer has no claimed profile with a recorded sex: show both forms
            forms = [speaker[s]["term"] for s in ("male", "female") if s in speaker]
            return Resolved(pattern, " / ".join(forms), entry["transliteration"], alternatives=forms)
    rule = entry.get("age")
    if rule is None:
        return Resolved(pattern, entry["term"], entry["transliteration"])
    age = next((a for a in ages if a.chain_index == rule["index"]), None)
    if age is None or age.order == "unknown":
        return Resolved(
            pattern,
            entry["term"],
            entry["transliteration"],
            alternatives=[rule["elder"]["term"], rule["younger"]["term"]],
            basis="unknown" if age is not None else None,
            age_order="unknown" if age is not None else None,
        )
    chosen = rule[age.order]
    return Resolved(pattern, chosen["term"], chosen["transliteration"], basis=age.basis, age_order=age.order)


def describe(pack: dict[str, Any], chain: Sequence[str], ages: Sequence[Age] = ()) -> str:
    """A literal reading of the chain in the pack's language ("पिता के बड़े भाई"); always available."""
    known = {a.chain_index: a.order for a in ages if a.order != "unknown"}
    out = ""
    for i, w in enumerate(chain):
        order = known.get(i)
        aged = pack.get("aged_words", {}).get(w, {})
        word = (aged.get(order) if order else None) or pack["words"].get(w) or w.replace("_", " ")
        out = word if i == 0 else pack["joiner"].format(acc=out, word=word)
    return out
