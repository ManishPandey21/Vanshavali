"""Lunar (tithi) dates as families write them (ADR-0022 §2).

A lunar date is kept exactly as entered: month (masa), fortnight (paksha), tithi, whether the
month was an adhik (extra) month, the month convention it was written in, and the samvat year
when known. It never fills in a Gregorian date, and is never filled in from one; converting is a
confirmed suggestion.

Internally months are numbered 1-12 from Chaitra, tithis 1-15 within a paksha (shukla 15 =
Purnima, krishna 15 = Amavasya), and an absolute tithi index 0-29 counts from shukla Pratipada.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

MASAS: tuple[str, ...] = (
    "chaitra",
    "vaishakha",
    "jyeshtha",
    "ashadha",
    "shravana",
    "bhadrapada",
    "ashvin",
    "kartika",
    "margashirsha",
    "pausha",
    "magha",
    "phalguna",
)
MASA_LABELS: dict[str, tuple[str, str]] = {
    "chaitra": ("Chaitra", "चैत्र"),
    "vaishakha": ("Vaishakha", "वैशाख"),
    "jyeshtha": ("Jyeshtha", "ज्येष्ठ"),
    "ashadha": ("Ashadha", "आषाढ़"),
    "shravana": ("Shravana", "श्रावण"),
    "bhadrapada": ("Bhadrapada", "भाद्रपद"),
    "ashvin": ("Ashvin", "आश्विन"),
    "kartika": ("Kartika", "कार्तिक"),
    "margashirsha": ("Margashirsha", "मार्गशीर्ष"),
    "pausha": ("Pausha", "पौष"),
    "magha": ("Magha", "माघ"),
    "phalguna": ("Phalguna", "फाल्गुन"),
}
TITHI_LABELS: tuple[tuple[str, str], ...] = (
    ("Pratipada", "प्रतिपदा"),
    ("Dvitiya", "द्वितीया"),
    ("Tritiya", "तृतीया"),
    ("Chaturthi", "चतुर्थी"),
    ("Panchami", "पंचमी"),
    ("Shashthi", "षष्ठी"),
    ("Saptami", "सप्तमी"),
    ("Ashtami", "अष्टमी"),
    ("Navami", "नवमी"),
    ("Dashami", "दशमी"),
    ("Ekadashi", "एकादशी"),
    ("Dvadashi", "द्वादशी"),
    ("Trayodashi", "त्रयोदशी"),
    ("Chaturdashi", "चतुर्दशी"),
)


class Paksha(StrEnum):
    SHUKLA = "shukla"
    KRISHNA = "krishna"


class MonthConvention(StrEnum):
    """How a lunar month is bounded: new moon to new moon, or full moon to full moon."""

    AMANTA = "amanta"
    PURNIMANTA = "purnimanta"


class Samvat(StrEnum):
    VIKRAM = "vikram"
    SHAKA = "shaka"


class LunarDate(BaseModel):
    """The lunar part of a date, as entered (stored inside the date JSON)."""

    model_config = ConfigDict(extra="forbid")

    masa: str = Field(pattern="^(" + "|".join(MASAS) + ")$")
    paksha: Paksha
    tithi: int = Field(ge=1, le=15)
    is_adhik: bool = False
    month_convention: MonthConvention
    samvat: Samvat | None = None
    year: int | None = Field(default=None, ge=1, le=9999)  # a samvat year, when known

    def label(self, lang: str = "en") -> str:
        hi = lang.startswith("hi")
        m = MASA_LABELS[self.masa][1 if hi else 0]
        adhik = ("अधिक " if hi else "Adhik ") if self.is_adhik else ""
        p = {"shukla": ("Shukla", "शुक्ल"), "krishna": ("Krishna", "कृष्ण")}[self.paksha.value][1 if hi else 0]
        t = tithi_label(self.paksha, self.tithi, lang)
        out = f"{adhik}{m} {p} {t}"
        if self.year and self.samvat:
            names = {Samvat.VIKRAM: ("Vikram Samvat", "विक्रम संवत"), Samvat.SHAKA: ("Shaka", "शक संवत")}
            out += f", {names[self.samvat][1 if hi else 0]} {self.year}"
        return out


def tithi_label(paksha: Paksha, tithi: int, lang: str = "en") -> str:
    hi = 1 if lang.startswith("hi") else 0
    if tithi == 15:
        return ("Purnima", "पूर्णिमा")[hi] if paksha == Paksha.SHUKLA else ("Amavasya", "अमावस्या")[hi]
    return TITHI_LABELS[tithi - 1][hi]


def masa_number(masa: str) -> int:
    """1 = Chaitra … 12 = Phalguna."""
    return MASAS.index(masa) + 1


def tithi_index(paksha: Paksha, tithi: int) -> int:
    """0 = shukla Pratipada … 14 = Purnima, 15 = krishna Pratipada … 29 = Amavasya."""
    return (0 if paksha == Paksha.SHUKLA else 15) + tithi - 1


def to_amanta_masa(masa: int, paksha: Paksha, convention: MonthConvention) -> int:
    """The amanta month a date written in ``convention`` falls in.

    The two systems agree in the shukla paksha. A purnimanta month starts at the full moon, so its
    krishna paksha precedes the shukla paksha of the same name: it is the krishna paksha of the
    *previous* amanta month.
    """
    if convention == MonthConvention.PURNIMANTA and paksha == Paksha.KRISHNA:
        return 12 if masa == 1 else masa - 1
    return masa


def from_amanta_masa(masa: int, paksha: Paksha, convention: MonthConvention) -> int:
    if convention == MonthConvention.PURNIMANTA and paksha == Paksha.KRISHNA:
        return 1 if masa == 12 else masa + 1
    return masa
