"""Land area units and square-metre normalisation (PRS §17.2).

The recorded area and unit are always stored unchanged. A normalised square-metre value is derived
**only** for units with a fixed, statute/convention-defined conversion. Units whose size varies by
state, district or even village (bigha, biswa, kanal, marla, …) get no normalised value: any single
conversion would be misleading, so the API returns ``area_sq_m = null`` with an explanatory note.
Conversions are exact decimals (no floats).
"""

from __future__ import annotations

from decimal import Decimal
from enum import StrEnum


class AreaUnit(StrEnum):
    BIGHA = "bigha"
    BISWA = "biswa"
    KANAL = "kanal"
    MARLA = "marla"
    GUNTHA = "guntha"
    CENT = "cent"
    ACRE = "acre"
    HECTARE = "hectare"
    SQ_M = "sq_m"
    SQ_FT = "sq_ft"
    GROUND = "ground"
    OTHER = "other"


_ACRE = Decimal("4046.8564224")
_SQ_FT = Decimal("0.09290304")

# square metres per unit — only units with a fixed conversion
FIXED_SQ_M: dict[AreaUnit, Decimal] = {
    AreaUnit.SQ_M: Decimal(1),
    AreaUnit.SQ_FT: _SQ_FT,
    AreaUnit.ACRE: _ACRE,
    AreaUnit.HECTARE: Decimal(10000),
    AreaUnit.CENT: _ACRE / 100,  # 1/100 acre = 435.6 sq ft
    AreaUnit.GUNTHA: _ACRE / 40,  # 1/40 acre = 1089 sq ft
    AreaUnit.GROUND: _SQ_FT * 2400,  # Tamil Nadu ground = 2400 sq ft
}

REGIONAL_NOTE = (
    "Regionally variable unit: its size differs by state and locality, so no square-metre value is "
    "derived. The recorded value is kept exactly as entered."
)
OTHER_NOTE = "Unit not standardised; the recorded value is kept exactly as entered."


def to_sq_m(area: Decimal | None, unit: str | None) -> tuple[Decimal | None, str | None]:
    """Return (square metres rounded to 0.01, note). Note explains when no value is derived."""
    if area is None or not unit:
        return None, None
    try:
        u = AreaUnit(unit)
    except ValueError:
        return None, OTHER_NOTE
    factor = FIXED_SQ_M.get(u)
    if factor is None:
        return None, OTHER_NOTE if u == AreaUnit.OTHER else REGIONAL_NOTE
    return (Decimal(area) * factor).quantize(Decimal("0.01")), None
