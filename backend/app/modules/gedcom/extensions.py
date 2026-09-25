"""The Vanshavali Indian GEDCOM extension vocabulary (ADR-0008; docs/gedcom/indian-extensions.md).

Every tag is documented in ``HEAD.SCHMA`` as ``2 TAG <tag> <URI>`` where the URI is
``{settings.gedcom_ext_base_uri}{slug}``. On import the URI is authoritative: a file that uses a
different tag name for one of our URIs maps correctly, and a file that reuses one of our tag names
for a *different* URI is treated as an unknown extension. Without a SCHMA entry we fall back to the
tag name.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings
from app.models.enums import HeritageAttribute

KIND_ASSERTION = "assertion"  # → heritage Assertion (USER_ASSERTION, provenance gedcom)
KIND_ASTROLOGY = "astrology"  # → AstrologyProfile (provenance_kind imported)
KIND_BIRTH_TIME = "birth_time"  # ↔ birth event time precision / source
KIND_PRESERVED = "preserved"  # recognised but stored verbatim (never auto-linked)


@dataclass(frozen=True)
class ExtensionDef:
    tag: str
    slug: str
    kind: str
    context: str  # where the structure appears
    payload: str  # GEDCOM payload datatype
    target: str | None  # HeritageAttribute value / AstrologyProfile column / None
    description: str

    @property
    def uri(self) -> str:
        return f"{get_settings().gedcom_ext_base_uri}{self.slug}"


EXTENSIONS: tuple[ExtensionDef, ...] = (
    ExtensionDef("_IND_GOTRA", "gotra", KIND_ASSERTION, "INDI", "Text", HeritageAttribute.GOTRA.value,
                 "Gotra (patrilineal clan lineage) as stated by the family or a source."),
    ExtensionDef("_IND_PRAVARA", "pravara", KIND_ASSERTION, "INDI", "Text", HeritageAttribute.PRAVARA.value,
                 "Pravara (list of rishis associated with the gotra)."),
    ExtensionDef("_IND_KULA", "kula", KIND_ASSERTION, "INDI", "Text", HeritageAttribute.KULA_OR_VAMSHA.value,
                 "Kula / vamsha (family line or dynasty name)."),
    ExtensionDef("_IND_ANCESTRAL_PLACE", "ancestral-place", KIND_ASSERTION, "INDI", "Text",
                 HeritageAttribute.ANCESTRAL_VILLAGE.value,
                 "Ancestral village or native place (mool gaon / sontha ooru)."),
    ExtensionDef("_IND_KULADEVATA", "kuladevata", KIND_ASSERTION, "INDI", "Text",
                 HeritageAttribute.KULADEVATA.value, "Family deity (kuladevata)."),
    ExtensionDef("_IND_KULADEVI", "kuladevi", KIND_ASSERTION, "INDI", "Text", HeritageAttribute.KULADEVI.value,
                 "Family goddess (kuladevi)."),
    ExtensionDef("_IND_THARAVAD", "tharavad", KIND_ASSERTION, "INDI", "Text",
                 HeritageAttribute.THARAVAD_OR_EQUIVALENT.value,
                 "Tharavad (Kerala matrilineal joint-family house) or an equivalent ancestral house name."),
    ExtensionDef("_IND_NAKSHATRA", "nakshatra", KIND_ASTROLOGY, "INDI", "Text", "nakshatra",
                 "Birth nakshatra (lunar mansion) as recorded, e.g. in a kundli."),
    ExtensionDef("_IND_NAKSHATRA_PADA", "nakshatra-pada", KIND_ASTROLOGY, "INDI", "Integer (1-4)",
                 "nakshatra_pada", "Quarter (pada) of the birth nakshatra."),
    ExtensionDef("_IND_RASHI", "rashi", KIND_ASTROLOGY, "INDI", "Text", "rashi",
                 "Moon sign (rashi) as recorded."),
    ExtensionDef("_IND_LAGNA", "lagna", KIND_ASTROLOGY, "INDI", "Text", "lagna",
                 "Ascendant (lagna) as recorded."),
    ExtensionDef("_IND_BIRTH_TIME_CONF", "birth-time-confidence", KIND_BIRTH_TIME, "INDI.BIRT", "Text",
                 None, "Precision and source of the birth TIME: '<precision> [<source>]'."),
    ExtensionDef("_IND_PROPERTY_REF", "property-ref", KIND_PRESERVED, "INDI", "Text", None,
                 "Opaque reference to a family property/land record. Preserved verbatim; never auto-linked."),
)  # fmt: skip

BY_TAG = {e.tag: e for e in EXTENSIONS}
BY_SLUG = {e.slug: e for e in EXTENSIONS}
BY_ATTRIBUTE = {e.target: e for e in EXTENSIONS if e.kind == KIND_ASSERTION}
ASTROLOGY_FIELDS = [e for e in EXTENSIONS if e.kind == KIND_ASTROLOGY]
_DEFAULT_BASE = "https://vanshavali.app/gedcom/ext/v1/"


def by_uri(uri: str) -> ExtensionDef | None:
    uri = uri.strip()
    for base in {get_settings().gedcom_ext_base_uri, _DEFAULT_BASE}:
        if uri.startswith(base):
            return BY_SLUG.get(uri[len(base) :].strip("/"))
    return None


def resolve(tag: str, schema: dict[str, str]) -> ExtensionDef | None:
    """Map a file's extension tag to our vocabulary: by SCHMA URI first, then by tag name."""
    uri = schema.get(tag.upper())
    if uri:
        return by_uri(uri)  # a documented URI that isn't ours is a foreign extension
    return BY_TAG.get(tag.upper())


def schema_lines(tags: set[str]) -> list[tuple[str, str]]:
    return [(e.tag, e.uri) for e in EXTENSIONS if e.tag in tags]
