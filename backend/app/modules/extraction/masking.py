"""Aadhaar masking (implementation plan §13.7): Aadhaar numbers are never stored.

An Aadhaar number is 12 digits, never starting with 0 or 1, usually printed as 4-4-4. Any such
sequence (ASCII or Devanagari digits, separated by spaces/hyphens/dots or not at all) is replaced
before OCR text or proposals are persisted.
"""

from __future__ import annotations

import re
from typing import Any

_D = "[0-9०-९]"
_D_FIRST = "[2-9२-९]"
_SEP = r"[ \-.–]?"
AADHAAR_RE = re.compile(rf"(?<![0-9०-९]){_D_FIRST}{_D}{{3}}{_SEP}{_D}{{4}}{_SEP}{_D}{{4}}(?![0-9०-९])")
MASK = "XXXX XXXX XXXX"


def mask_aadhaar(text: str) -> str:
    return AADHAAR_RE.sub(MASK, text)


def contains_aadhaar(text: str) -> bool:
    return AADHAAR_RE.search(text) is not None


def mask_value(value: Any) -> Any:
    """Recursively mask strings inside JSON-like values."""
    if isinstance(value, str):
        return mask_aadhaar(value)
    if isinstance(value, dict):
        return {k: mask_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [mask_value(v) for v in value]
    return value
