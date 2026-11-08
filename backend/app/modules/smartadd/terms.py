"""Kinship terms as paths of basic edges (ADR-0020 §1).

A term is a *controlled* system value: the code says which edges to walk or create, never a stored
relationship. Words and translations live in the UI locale files (``smartAdd.terms.<code>``).

Every path is read from the anchor's point of view (the person whose profile the user is on).
``age`` on a sibling hop says how the person reached by that hop compares with the previous person
on the path: ``tau`` is the father's *elder* brother, ``devar`` the husband's *younger* brother.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Relation = Literal["parent", "child", "sibling", "spouse"]
Sex = Literal["male", "female"]
AgeOrder = Literal["elder", "younger"]


@dataclass(frozen=True)
class Hop:
    relation: Relation
    sex: Sex | None = None  # None: either (e.g. "spouse" in sasur)
    age: AgeOrder | None = None  # only on sibling hops


@dataclass(frozen=True)
class Term:
    code: str
    group: Literal["direct", "grandparents", "paternal", "maternal", "siblings", "children", "in_laws"]
    hops: tuple[Hop, ...]

    @property
    def target(self) -> Hop:
        return self.hops[-1]

    @property
    def intermediates(self) -> tuple[Hop, ...]:
        return self.hops[:-1]


def _p(sex: Sex | None = None) -> Hop:
    return Hop("parent", sex)


def _c(sex: Sex | None = None) -> Hop:
    return Hop("child", sex)


def _s(sex: Sex | None = None, age: AgeOrder | None = None) -> Hop:
    return Hop("sibling", sex, age)


def _sp(sex: Sex | None = None) -> Hop:
    return Hop("spouse", sex)


M: Sex = "male"
F: Sex = "female"

_ALL: tuple[Term, ...] = (
    # direct
    Term("father", "direct", (_p(M),)),
    Term("mother", "direct", (_p(F),)),
    Term("husband", "direct", (_sp(M),)),
    Term("wife", "direct", (_sp(F),)),
    Term("son", "direct", (_c(M),)),
    Term("daughter", "direct", (_c(F),)),
    Term("brother", "direct", (_s(M),)),
    Term("sister", "direct", (_s(F),)),
    # grandparents
    Term("dada", "grandparents", (_p(M), _p(M))),
    Term("dadi", "grandparents", (_p(M), _p(F))),
    Term("nana", "grandparents", (_p(F), _p(M))),
    Term("nani", "grandparents", (_p(F), _p(F))),
    # father's side
    Term("tau", "paternal", (_p(M), _s(M, "elder"))),
    Term("tai", "paternal", (_p(M), _s(M, "elder"), _sp(F))),
    Term("chacha", "paternal", (_p(M), _s(M, "younger"))),
    Term("chachi", "paternal", (_p(M), _s(M, "younger"), _sp(F))),
    Term("bua", "paternal", (_p(M), _s(F))),
    Term("fufa", "paternal", (_p(M), _s(F), _sp(M))),
    # mother's side
    Term("mama", "maternal", (_p(F), _s(M))),
    Term("mami", "maternal", (_p(F), _s(M), _sp(F))),
    Term("mausi", "maternal", (_p(F), _s(F))),
    Term("mausa", "maternal", (_p(F), _s(F), _sp(M))),
    # siblings and their families
    Term("bhaiya", "siblings", (_s(M, "elder"),)),
    Term("didi", "siblings", (_s(F, "elder"),)),
    Term("bhabhi", "siblings", (_s(M), _sp(F))),
    Term("jija", "siblings", (_s(F), _sp(M))),
    Term("bhatija", "siblings", (_s(M), _c(M))),
    Term("bhatiji", "siblings", (_s(M), _c(F))),
    Term("bhanja", "siblings", (_s(F), _c(M))),
    Term("bhanji", "siblings", (_s(F), _c(F))),
    # children's families
    Term("bahu", "children", (_c(M), _sp(F))),
    Term("damaad", "children", (_c(F), _sp(M))),
    Term("pota", "children", (_c(M), _c(M))),
    Term("poti", "children", (_c(M), _c(F))),
    Term("nati", "children", (_c(F), _c(M))),
    Term("natin", "children", (_c(F), _c(F))),
    # in-laws
    Term("sasur", "in_laws", (_sp(), _p(M))),
    Term("saas", "in_laws", (_sp(), _p(F))),
    Term("jeth", "in_laws", (_sp(M), _s(M, "elder"))),
    Term("jethani", "in_laws", (_sp(M), _s(M, "elder"), _sp(F))),
    Term("devar", "in_laws", (_sp(M), _s(M, "younger"))),
    Term("devrani", "in_laws", (_sp(M), _s(M, "younger"), _sp(F))),
    Term("nanad", "in_laws", (_sp(M), _s(F))),
    Term("nandoi", "in_laws", (_sp(M), _s(F), _sp(M))),
    Term("bhai_sahab", "in_laws", (_sp(F), _s(M, "elder"))),
    Term("saala", "in_laws", (_sp(F), _s(M, "younger"))),
    Term("sahlaj", "in_laws", (_sp(F), _s(M), _sp(F))),
    Term("saali", "in_laws", (_sp(F), _s(F))),
    Term("sadhu", "in_laws", (_sp(F), _s(F), _sp(M))),
    Term("samdhi", "in_laws", (_c(), _sp(), _p(M))),
    Term("samdhan", "in_laws", (_c(), _sp(), _p(F))),
)

TERMS: dict[str, Term] = {t.code: t for t in _ALL}
if len(TERMS) != len(_ALL):  # pragma: no cover - guards the table above
    raise RuntimeError("duplicate term code")
