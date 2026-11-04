"""Read-only queries over the reference vocabularies (ADR-0019).

Search is ranked: a whole name (label, translation or alias) equal to the query, then a name
starting with it, then any name containing it, then trigram similarity; ties by the list's own order.
Queries are romanised with the same normaliser as the stored keys, so any script matches any script.
"""

from __future__ import annotations

from sqlalchemy import case, func, literal, or_, select
from sqlalchemy.orm import Session, aliased

from app.api.schemas import Page, decode_cursor, encode_cursor
from app.core.errors import NotFound
from app.core.textnorm import romanize
from app.models import Vocabulary, VocabularyTerm
from app.modules.vocabulary.schemas import TermOut, VocabularyOut

SIMILARITY_THRESHOLD = 0.5


def list_vocabularies(db: Session) -> list[VocabularyOut]:
    counts = dict(
        db.execute(
            select(VocabularyTerm.vocabulary_code, func.count())
            .where(VocabularyTerm.is_active.is_(True))
            .group_by(VocabularyTerm.vocabulary_code)
        ).all()
    )
    return [
        VocabularyOut(
            code=v.code,
            name=v.name,
            description=v.description,
            parent_vocabulary=v.parent_vocabulary_code,
            version=v.version,
            source=v.source,
            license=v.license,
            term_count=counts.get(v.code, 0),
        )
        for v in db.scalars(select(Vocabulary).order_by(Vocabulary.code))
    ]


def get_vocabulary(db: Session, code: str) -> Vocabulary:
    v = db.get(Vocabulary, code)
    if v is None:
        raise NotFound("Vocabulary not found")
    return v


def search_terms(
    db: Session,
    code: str,
    *,
    q: str | None = None,
    parent: str | None = None,
    tag: str | None = None,
    include_inactive: bool = False,
    cursor: str | None = None,
    limit: int = 50,
) -> Page[TermOut]:
    vocab = get_vocabulary(db, code)
    parent_term = aliased(VocabularyTerm)
    stmt = (
        select(VocabularyTerm, parent_term.code)
        .outerjoin(parent_term, parent_term.id == VocabularyTerm.parent_id)
        .where(VocabularyTerm.vocabulary_code == code)
    )
    if not include_inactive:
        stmt = stmt.where(VocabularyTerm.is_active.is_(True))
    if parent is not None:
        if vocab.parent_vocabulary_code is None:
            raise NotFound("This vocabulary has no parent vocabulary")
        parent_id = db.scalar(
            select(VocabularyTerm.id).where(
                VocabularyTerm.vocabulary_code == vocab.parent_vocabulary_code, VocabularyTerm.code == parent
            )
        )
        if parent_id is None:
            raise NotFound("Parent term not found")
        stmt = stmt.where(VocabularyTerm.parent_id == parent_id)
    if tag is not None:
        stmt = stmt.where(VocabularyTerm.tags.contains([tag]))

    key = romanize(q or "")
    if key:
        # keys are lowercase [0-9a-z ] only (romanize), so they are safe inside LIKE and regex patterns
        st = VocabularyTerm.search_text
        exact = st.op("~")(literal(rf"(^| \| ){key}( \| |$)"))
        prefix = st.op("~")(literal(rf"(^| \| ){key}"))
        word_prefix = st.op("~")(literal(rf"(^| ){key}"))
        contains = st.like(f"%{key}%")
        similarity = func.word_similarity(key, st)
        stmt = stmt.where(or_(contains, similarity >= SIMILARITY_THRESHOLD)).order_by(
            case((exact, 0), (prefix, 1), (word_prefix, 2), (contains, 3), else_=4),
            similarity.desc(),
            VocabularyTerm.sort_order,
            VocabularyTerm.label,
        )
    else:
        stmt = stmt.order_by(VocabularyTerm.sort_order, VocabularyTerm.label)

    offset = decode_cursor(cursor)
    rows = db.execute(stmt.offset(offset).limit(limit + 1)).all()
    items = [
        TermOut(
            code=t.code,
            label=t.label,
            labels=t.labels,
            aliases=t.aliases,
            tags=t.tags,
            attributes=t.attributes,
            parent_code=parent_code,
            is_active=t.is_active,
        )
        for t, parent_code in rows[:limit]
    ]
    return Page(items=items, next_cursor=encode_cursor(offset + limit) if len(rows) > limit else None)
