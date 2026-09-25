"""Tiered name matching inside PostgreSQL with explainable match reasons (ADR-0007, PRS §23)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text

from app.authz.context import TreeContext
from app.core.textnorm import phonetic_key, search_key

WORD_SIMILARITY_MIN = 0.45


@dataclass
class NameMatch:
    person_id: uuid.UUID
    name_id: uuid.UUID
    score: float
    tier: str  # exact | prefix | contains | fuzzy | phonetic
    matched_text: str
    reason: str


def match_names(ctx: TreeContext, query: str, limit: int = 500) -> list[NameMatch]:
    """Best match per person, ordered by score. Callers MUST privacy-filter the person ids."""
    q = search_key(query)
    if not q:
        return []
    ph = [t for t in phonetic_key(query).split() if t]
    rows = ctx.db.execute(
        text(
            """
            SELECT n.person_id, n.id,
                   coalesce(nullif(n.full_name_as_recorded, ''), concat_ws(' ', n.given_name, n.surname)) AS shown,
                   n.search_text,
                   n.search_text = :q AS is_exact,
                   (n.search_text LIKE :q || '%' OR n.search_text LIKE '% ' || :q || '%') AS is_prefix,
                   position(:q in n.search_text) > 0 AS is_contains,
                   word_similarity(:q, n.search_text) AS wsim,
                   CASE WHEN cardinality(CAST(:ph AS text[])) > 0
                        THEN string_to_array(n.search_phonetic, ' ') @> CAST(:ph AS text[]) ELSE false END AS is_phonetic
              FROM name_record n JOIN person p ON p.id = n.person_id AND p.tree_id = n.tree_id
             WHERE n.tree_id = :tree AND p.deleted_at IS NULL
               AND (position(:q in n.search_text) > 0
                    OR word_similarity(:q, n.search_text) >= :wsim_min
                    OR (cardinality(CAST(:ph AS text[])) > 0
                        AND string_to_array(n.search_phonetic, ' ') @> CAST(:ph AS text[])))
             LIMIT :limit
            """
        ),
        {"q": q, "ph": ph, "tree": ctx.tree_id, "wsim_min": WORD_SIMILARITY_MIN, "limit": limit * 4},
    ).all()
    best: dict[uuid.UUID, NameMatch] = {}
    for pid, nid, shown, _stext, is_exact, is_prefix, is_contains, wsim, _is_phon in rows:
        if is_exact:
            m = NameMatch(pid, nid, 1.0, "exact", shown, f'exact match on "{shown}"')
        elif is_prefix:
            m = NameMatch(pid, nid, 0.9, "prefix", shown, f'name "{shown}" starts with "{query}"')
        elif is_contains:
            m = NameMatch(pid, nid, 0.8, "contains", shown, f'name "{shown}" contains "{query}"')
        elif wsim >= WORD_SIMILARITY_MIN:
            m = NameMatch(
                pid,
                nid,
                0.4 + 0.35 * float(wsim),
                "fuzzy",
                shown,
                f'"{query}" ≈ "{shown}" (similarity {float(wsim):.2f})',
            )
        else:
            m = NameMatch(pid, nid, 0.4, "phonetic", shown, f'"{query}" sounds like "{shown}"')
        cur = best.get(pid)
        if cur is None or m.score > cur.score:
            best[pid] = m
    return sorted(best.values(), key=lambda m: (-m.score, m.matched_text))[:limit]
