"""LGD levels, their parents, and the name each state uses for its sub-districts (ADR-0019 §5)."""

from __future__ import annotations

from app.models.enums import GeoLevel

# the level a unit's parent normally has; urban local bodies hang off a district (or the state when
# the LGD file names no district)
PARENT_LEVEL: dict[GeoLevel, GeoLevel | None] = {
    GeoLevel.STATE: None,
    GeoLevel.DISTRICT: GeoLevel.STATE,
    GeoLevel.SUB_DISTRICT: GeoLevel.DISTRICT,
    GeoLevel.VILLAGE: GeoLevel.SUB_DISTRICT,
    GeoLevel.URBAN_BODY: GeoLevel.DISTRICT,
}

RANK: dict[GeoLevel, int] = {
    GeoLevel.STATE: 0,
    GeoLevel.DISTRICT: 1,
    GeoLevel.SUB_DISTRICT: 2,
    GeoLevel.VILLAGE: 3,
    GeoLevel.URBAN_BODY: 3,
}

# Import stages (ADR-0019 §1): which levels each stage loads.
STAGE_LEVELS: dict[int, tuple[GeoLevel, ...]] = {
    1: (GeoLevel.STATE, GeoLevel.DISTRICT, GeoLevel.SUB_DISTRICT),
    2: (GeoLevel.VILLAGE, GeoLevel.URBAN_BODY),
    3: (),  # the India Post PIN directory
}

# What each state calls its sub-district, keyed by LGD state code (the Census 2011 state codes).
# Reviewed mapping, shown through the i18n keys ``geo.subDistrict.<label>`` in English and Hindi.
# States not listed use the neutral "sub_district". Change only by code review.
SUB_DISTRICT_LABELS: dict[str, str] = {
    "1": "tehsil",  # Jammu and Kashmir
    "2": "tehsil",  # Himachal Pradesh
    "3": "tehsil",  # Punjab
    "5": "tehsil",  # Uttarakhand
    "6": "tehsil",  # Haryana
    "8": "tehsil",  # Rajasthan
    "9": "tehsil",  # Uttar Pradesh
    "10": "block",  # Bihar (CD blocks)
    "12": "circle",  # Arunachal Pradesh
    "18": "circle",  # Assam
    "19": "block",  # West Bengal (CD blocks)
    "20": "block",  # Jharkhand (CD blocks)
    "21": "tehsil",  # Odisha (tahasil)
    "22": "tehsil",  # Chhattisgarh
    "23": "tehsil",  # Madhya Pradesh
    "24": "taluka",  # Gujarat
    "27": "taluka",  # Maharashtra
    "28": "mandal",  # Andhra Pradesh
    "29": "taluka",  # Karnataka (taluk)
    "30": "taluka",  # Goa
    "32": "taluka",  # Kerala (taluk)
    "33": "taluka",  # Tamil Nadu (taluk)
    "36": "mandal",  # Telangana
    "11": "subdivision",  # Sikkim
    "14": "subdivision",  # Manipur
}

SUB_DISTRICT_LABEL_KEYS = ("sub_district", "tehsil", "taluka", "mandal", "block", "circle", "subdivision")


def sub_district_label(state_code: str | None) -> str:
    return SUB_DISTRICT_LABELS.get(state_code or "", "sub_district")
