"""``POST /transliterate``: name spelling suggestions in the other script (ADR-0025 §4).

Signed-in users only, size- and rate-limited. It reads no tree data, and the text is neither
logged nor stored: it is only passed to the engine and the candidates are returned.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUser
from app.core.ratelimit import enforce
from app.modules.translit import engine
from app.modules.translit.schemas import TransliterateIn, TransliterateOut, TransliterationCandidate

router = APIRouter(tags=["transliteration"])

# generous for typing pauses (debounced in the SPA), small enough to stop use as a free service
RATE_LIMIT_PER_MINUTE = 120


@router.post("/transliterate", response_model=TransliterateOut)
def transliterate(body: TransliterateIn, user: CurrentUser) -> TransliterateOut:
    enforce(f"translit:{user.id}", RATE_LIMIT_PER_MINUTE)
    cands = engine.suggest(body.text, body.target_script)
    return TransliterateOut(
        candidates=[TransliterationCandidate(text=c.text, method=c.method) for c in cands],
        engine=engine.ENGINE,
        version=engine.VERSION,
        lexicon_version=engine.lexicon().version,
    )
