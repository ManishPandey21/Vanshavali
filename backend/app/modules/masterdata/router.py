from __future__ import annotations

from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbDep, TreeCtx
from app.modules.masterdata import service
from app.modules.masterdata.schemas import TreeTermIn, TreeTermOut, VocabularyOut, VocabularyTermsOut

router = APIRouter(tags=["master-data"])

Lang = Query(default="en", max_length=16, pattern=r"^[a-z]{2,3}(-[A-Za-z]{2,4})?$")


@router.get("/vocabularies", response_model=list[VocabularyOut])
def list_vocabularies(user: CurrentUser, db: DbDep) -> list[VocabularyOut]:
    """Extensible vocabularies (ADR-0018). Controlled values are not listed here."""
    return service.list_vocabularies(db)


@router.get("/vocabularies/{key}", response_model=VocabularyTermsOut)
def vocabulary_terms(
    key: str,
    user: CurrentUser,
    db: DbDep,
    q: str = Query(default="", max_length=100),
    lang: str = Lang,
    parent: str | None = Query(default=None, max_length=80),
    include_retired: bool = False,
) -> VocabularyTermsOut:
    """Global suggestions, searchable by label in any script, alias or spelling."""
    vocab, items = service.global_terms(
        db, key, q=q, lang=lang, parent=parent, include_retired=include_retired
    )
    return VocabularyTermsOut(vocabulary=vocab, items=items)


@router.get("/trees/{tree_id}/vocabularies/{key}", response_model=VocabularyTermsOut)
def tree_vocabulary_terms(
    key: str, ctx: TreeCtx, q: str = Query(default="", max_length=100), lang: str = Lang
) -> VocabularyTermsOut:
    """Global suggestions plus this family's own entries."""
    vocab, items = service.tree_terms(ctx, key, q=q, lang=lang)
    return VocabularyTermsOut(vocabulary=vocab, items=items)


@router.post(
    "/trees/{tree_id}/vocabularies/{key}/terms",
    response_model=TreeTermOut,
    status_code=status.HTTP_201_CREATED,
    responses={200: {"model": TreeTermOut, "description": "The label already names an entry"}},
)
def add_tree_term(key: str, body: TreeTermIn, ctx: TreeCtx, lang: str = Lang) -> TreeTermOut | JSONResponse:
    """Add the family's own entry ("Add my own"); an existing matching entry is returned instead."""
    term, created = service.add_tree_term(ctx, key, body.label, body.aliases, lang)
    out = TreeTermOut(term=term, created=created)
    if created:
        return out
    return JSONResponse(out.model_dump(mode="json"), status_code=status.HTTP_200_OK)
