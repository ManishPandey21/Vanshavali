"""Read-only reference vocabularies for searchable fields (ADR-0019).

Global reference data, not tree data: any signed-in user may read it; nothing here writes.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Response

from app.api.deps import CurrentUser, DbDep
from app.api.schemas import Page
from app.modules.vocabulary import service
from app.modules.vocabulary.schemas import TermOut, VocabularyOut

router = APIRouter(prefix="/vocabularies", tags=["vocabularies"])

CACHE = "private, max-age=3600"


@router.get("", response_model=list[VocabularyOut])
def list_vocabularies(_: CurrentUser, db: DbDep, response: Response) -> list[VocabularyOut]:
    response.headers["Cache-Control"] = CACHE
    return service.list_vocabularies(db)


@router.get("/{code}/terms", response_model=Page[TermOut])
def list_terms(
    code: str,
    _: CurrentUser,
    db: DbDep,
    response: Response,
    q: str | None = Query(default=None, max_length=100, description="Search text in any script"),
    parent: str | None = Query(default=None, max_length=120, description="Parent term code (cascade)"),
    tag: str | None = Query(default=None, max_length=80),
    include_inactive: bool = False,
    cursor: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
) -> Page[TermOut]:
    response.headers["Cache-Control"] = CACHE
    return service.search_terms(
        db,
        code,
        q=q,
        parent=parent,
        tag=tag,
        include_inactive=include_inactive,
        cursor=cursor,
        limit=limit,
    )
