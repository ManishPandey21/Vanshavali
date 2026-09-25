"""Server-owned consent and attestation wording (ADR-0011).

The client shows the text returned here and posts back ``(version, language)``; the server stores
the SHA-256 of that exact text. Changing any wording means bumping the version, which makes older
attestations stale so users confirm the new text.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from app.core.errors import Conflict, NotFound, Unprocessable


class StatementKind(StrEnum):
    FAMILY_DATA = "family_data"  # the person adding relatives to a tree
    PROFILE_CLAIM = "profile_claim"  # a relative claiming their own profile through an invite


LANGUAGES = ("en", "hi")

_STATEMENTS: dict[StatementKind, tuple[str, dict[str, str]]] = {
    StatementKind.FAMILY_DATA: (
        "2026-09-v1",
        {
            "en": (
                "I agree to add my family members' names to this private tree, and I confirm I have "
                "their permission to do so."
            ),
            "hi": (
                "मैं अपने परिवार के सदस्यों के नाम इस निजी वंशवृक्ष में जोड़ने के लिए सहमत हूँ, और "
                "पुष्टि करता/करती हूँ कि ऐसा करने के लिए मेरे पास उनकी अनुमति है।"
            ),
        },
    ),
    StatementKind.PROFILE_CLAIM: (
        "2026-09-v1",
        {
            "en": (
                "This profile is about me. I agree that this private family tree may keep my name and "
                "the family details recorded about me, shown only to the people my privacy settings "
                "allow. After my claim is approved I can change those settings, withdraw this consent "
                "or ask for my profile to be erased at any time."
            ),
            "hi": (
                "यह प्रोफ़ाइल मेरी है। मैं सहमत हूँ कि यह निजी वंशवृक्ष मेरा नाम और मेरे बारे में दर्ज "
                "पारिवारिक जानकारी रख सकता है, जो केवल उन्हीं लोगों को दिखेगी जिन्हें मेरी गोपनीयता "
                "सेटिंग्स अनुमति देती हैं। मेरा दावा स्वीकृत होने के बाद मैं कभी भी ये सेटिंग्स बदल "
                "सकता/सकती हूँ, यह सहमति वापस ले सकता/सकती हूँ या अपनी प्रोफ़ाइल मिटाने का अनुरोध कर "
                "सकता/सकती हूँ।"
            ),
        },
    ),
}


@dataclass(frozen=True)
class Statement:
    kind: StatementKind
    version: str
    language: str
    text: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()


def _language(language: str | None) -> str:
    lang = (language or "en").split("-")[0].lower()
    return lang if lang in LANGUAGES else "en"


def current(kind: StatementKind, language: str | None = None) -> Statement:
    if kind not in _STATEMENTS:
        raise NotFound("Statement not found")
    version, texts = _STATEMENTS[kind]
    lang = _language(language)
    return Statement(kind=kind, version=version, language=lang, text=texts[lang])


def current_version(kind: StatementKind) -> str:
    return _STATEMENTS[kind][0]


def verify(kind: StatementKind, version: str, language: str) -> Statement:
    """The statement the client says it showed; refuses stale versions and unknown languages."""
    if language not in LANGUAGES:
        raise Unprocessable("Unsupported statement language", code="unsupported_language")
    stmt = current(kind, language)
    if version != stmt.version:
        raise Conflict(
            "The wording has changed. Please read the updated statement and confirm again.",
            code="statement_outdated",
            details={"current_version": stmt.version},
        )
    return stmt
