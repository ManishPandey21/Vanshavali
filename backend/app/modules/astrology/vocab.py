"""Jyotish vocabularies (PRS §11): 27 nakshatras, 12 rashis, tithis, pakshas and ayanamshas.

Each canonical value lists common romanised spellings and Hindi/Sanskrit (Devanagari), Tamil and
Telugu forms. These lists are used ONLY to validate and normalise values that a user entered or
that a document states — never to derive one value from another (e.g. rashi from nakshatra).
"""

from __future__ import annotations

import re
import unicodedata

NAKSHATRAS: dict[str, tuple[str, ...]] = {
    "Ashwini": ("Aswini", "Ashvini", "Asvini", "अश्विनी", "அசுவனி", "అశ్విని"),
    "Bharani": ("Bharni", "भरणी", "பரணி", "భరణి"),
    "Krittika": ("Kritika", "Krithika", "Kruthika", "Karthigai", "कृत्तिका", "कृतिका", "கிருத்திகை", "కృత్తిక"),
    "Rohini": ("Rohani", "रोहिणी", "ரோகிணி", "రోహిణి"),
    "Mrigashira": (
        "Mrigasira",
        "Mrigshira",
        "Mrigasheersha",
        "Mrigashirsha",
        "Mrugasira",
        "मृगशिरा",
        "मृगशीर्ष",
        "மிருகசிரிஷம்",
        "మృగశిర",
    ),
    "Ardra": ("Aardra", "Arudra", "Thiruvathirai", "आर्द्रा", "आद्रा", "திருவாதிரை", "ఆర్ద్ర"),
    "Punarvasu": ("Punarvasu", "Punarpoosam", "पुनर्वसु", "புனர்பூசம்", "పునర్వసు"),
    "Pushya": ("Pushyami", "Pooyam", "Poosam", "Pushyam", "पुष्य", "பூசம்", "పుష్యమి"),
    "Ashlesha": ("Aslesha", "Ashlesa", "Ayilyam", "आश्लेषा", "अश्लेषा", "ஆயில்யம்", "ఆశ్లేష"),
    "Magha": ("Makha", "Makam", "मघा", "மகம்", "మఖ"),
    "Purva Phalguni": (
        "Poorva Phalguni",
        "Purvaphalguni",
        "Purva Falguni",
        "Pubba",
        "Pooram",
        "पूर्वाफाल्गुनी",
        "पूर्व फाल्गुनी",
        "पूर्वा फाल्गुनी",
        "பூரம்",
    ),
    "Uttara Phalguni": (
        "Uttaraphalguni",
        "Uttara Falguni",
        "Uthram",
        "Uttiram",
        "उत्तराफाल्गुनी",
        "उत्तर फाल्गुनी",
        "उत्तरा फाल्गुनी",
        "உத்திரம்",
    ),
    "Hasta": ("Hastha", "Hastham", "हस्त", "ஹஸ்தம்", "హస్త"),
    "Chitra": ("Chithra", "Chitta", "Chithirai", "चित्रा", "சித்திரை", "చిత్త"),
    "Swati": ("Svati", "Swathi", "Swaati", "स्वाति", "स्वाती", "சுவாதி", "స్వాతి"),
    "Vishakha": ("Visakha", "Vishaka", "Visakam", "विशाखा", "விசாகம்", "విశాఖ"),
    "Anuradha": ("Anuradha", "Anusham", "Anizham", "अनुराधा", "அனுஷம்", "అనూరాధ"),
    "Jyeshtha": ("Jyeshta", "Jyestha", "Jyeshtha", "Kettai", "Kéttai", "ज्येष्ठा", "கேட்டை", "జ్యేష్ఠ"),
    "Mula": ("Moola", "Moolam", "Mool", "मूल", "மூலம்", "మూల"),
    "Purva Ashadha": (
        "Poorvashada",
        "Purvashadha",
        "Purvashada",
        "Poorva Ashadha",
        "Pooradam",
        "पूर्वाषाढ़ा",
        "पूर्वाषाढा",
        "पूर्वाषाढ",
        "பூராடம்",
    ),
    "Uttara Ashadha": (
        "Uttarashada",
        "Uttarashadha",
        "Uthrashada",
        "Uthiradam",
        "उत्तराषाढ़ा",
        "उत्तराषाढा",
        "உத்திராடம்",
    ),
    "Shravana": ("Sravana", "Shravan", "Shrawan", "Thiruvonam", "Sravanam", "श्रवण", "திருவோணம்", "శ్రవణం"),
    "Dhanishta": ("Dhanishtha", "Dhanista", "Shravishtha", "Avittam", "धनिष्ठा", "धनिष्ठा", "அவிட்டம்", "ధనిష్ఠ"),
    "Shatabhisha": (
        "Satabhisha",
        "Shatabhishak",
        "Shatataraka",
        "Sathayam",
        "Shatbhisha",
        "शतभिषा",
        "शतभिषक",
        "சதயம்",
        "శతభిషం",
    ),
    "Purva Bhadrapada": (
        "Poorva Bhadrapada",
        "Purvabhadrapada",
        "Poorvabhadra",
        "Purva Bhadra",
        "Poorattathi",
        "पूर्वाभाद्रपद",
        "पूर्वा भाद्रपद",
        "पूर्व भाद्रपद",
        "பூரட்டாதி",
    ),
    "Uttara Bhadrapada": (
        "Uttarabhadrapada",
        "Uttarabhadra",
        "Uttara Bhadra",
        "Uthrattathi",
        "उत्तराभाद्रपद",
        "उत्तरा भाद्रपद",
        "उत्तर भाद्रपद",
        "உத்திரட்டாதி",
    ),
    "Revati": ("Revathi", "Revathy", "रेवती", "ரேவதி", "రేవతి"),
}

RASHIS: dict[str, tuple[str, ...]] = {
    "Mesha": ("Mesh", "Mesham", "Aries", "मेष", "மேஷம்", "మేషం"),
    "Vrishabha": ("Vrishabh", "Vrushabh", "Vrishabham", "Rishabam", "Taurus", "वृषभ", "वृष", "ரிஷபம்", "వృషభం"),
    "Mithuna": ("Mithun", "Mithunam", "Gemini", "मिथुन", "மிதுனம்", "మిథునం"),
    "Karka": ("Kark", "Karkata", "Kataka", "Karkatakam", "Kadagam", "Cancer", "कर्क", "கடகம்", "కర్కాటకం"),
    "Simha": ("Singh", "Simham", "Leo", "सिंह", "சிம்மம்", "సింహం"),
    "Kanya": ("Kanni", "Virgo", "कन्या", "கன்னி", "కన్య"),
    "Tula": ("Tul", "Thula", "Thulam", "Libra", "तुला", "துலாம்", "తుల"),
    "Vrischika": (
        "Vrishchik",
        "Vrishchika",
        "Vruschika",
        "Vrischikam",
        "Scorpio",
        "वृश्चिक",
        "விருச்சிகம்",
        "వృశ్చికం",
    ),
    "Dhanu": ("Dhanus", "Dhanush", "Dhanusu", "Sagittarius", "धनु", "தனுசு", "ధనస్సు"),
    "Makara": ("Makar", "Makaram", "Capricorn", "मकर", "மகரம்", "మకరం"),
    "Kumbha": ("Kumbh", "Kumbham", "Aquarius", "कुंभ", "कुम्भ", "கும்பம்", "కుంభం"),
    "Meena": ("Meen", "Meenam", "Pisces", "मीन", "மீனம்", "మీనం"),
}

TITHIS: dict[str, tuple[str, ...]] = {
    "Pratipada": ("Pratipat", "Prathama", "Padyami", "प्रतिपदा", "प्रथमा", "पड़वा", "परिवा"),
    "Dwitiya": ("Dvitiya", "Dwiteeya", "Vidiya", "द्वितीया", "दूज"),
    "Tritiya": ("Trithiya", "Tritheeya", "Thadiya", "तृतीया", "तीज"),
    "Chaturthi": ("Chathurthi", "Chauth", "चतुर्थी", "चौथ"),
    "Panchami": ("Panchmi", "पंचमी", "पञ्चमी"),
    "Shashthi": ("Shasthi", "Sashti", "Shashti", "Chhath", "षष्ठी", "छठ"),
    "Saptami": ("Sapthami", "सप्तमी"),
    "Ashtami": ("Ashthami", "Atham", "अष्टमी"),
    "Navami": ("Navmi", "नवमी"),
    "Dashami": ("Dasami", "Dasmi", "दशमी"),
    "Ekadashi": ("Ekadasi", "Ekadasee", "Gyaras", "एकादशी", "ग्यारस"),
    "Dwadashi": ("Dvadashi", "Dwadasi", "Baras", "द्वादशी", "बारस"),
    "Trayodashi": ("Trayodasi", "Teras", "त्रयोदशी", "तेरस"),
    "Chaturdashi": ("Chathurdasi", "Chaturdasi", "Chaudas", "चतुर्दशी", "चौदस"),
    "Purnima": ("Poornima", "Pournami", "Pournima", "Purnamasi", "पूर्णिमा", "पूर्णमासी", "पूनम"),
    "Amavasya": ("Amavasai", "Amavas", "Amawasya", "अमावस्या", "अमावस"),
}

PAKSHAS: dict[str, tuple[str, ...]] = {
    "Shukla": ("Sukla", "Shukl", "Shudi", "Sudi", "Bright", "Waxing", "शुक्ल", "सुदी"),
    "Krishna": ("Krushna", "Vadi", "Badi", "Dark", "Waning", "कृष्ण", "वदी", "बदी"),
}

AYANAMSHAS: dict[str, tuple[str, ...]] = {
    "Lahiri": ("Chitrapaksha", "Chitra Paksha", "लाहिरी", "चित्रपक्ष"),
    "Raman": ("B.V. Raman", "BV Raman", "रमन"),
    "Krishnamurti": ("KP", "K.P.", "Krishnamurthy", "कृष्णमूर्ति"),
    "Yukteshwar": ("Sri Yukteswar", "Yukteswar", "युक्तेश्वर"),
    "Fagan-Bradley": ("Fagan Bradley", "Fagan/Bradley"),
    "Pushya-paksha": ("Pushya Paksha",),
    "True Chitra": ("True Chitrapaksha",),
    "Tropical": ("Sayana", "सायन"),
}

_LETTER = r"A-Za-zऀ-ॿ஀-௿ఀ-౿"


def _fold(text: str) -> str:
    """Lowercase, strip Latin diacritics, NFC for Indic; used for comparison only."""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(ch for ch in t if not (unicodedata.combining(ch) and ord(ch) < 0x0900))
    return unicodedata.normalize("NFC", t).lower()


def _compile(vocab: dict[str, tuple[str, ...]]) -> list[tuple[re.Pattern[str], str, int]]:
    out: list[tuple[re.Pattern[str], str, int]] = []
    for canonical, variants in vocab.items():
        for v in {canonical, *variants}:
            parts = [re.escape(_fold(p)) for p in re.split(r"[\s\-./]+", v) if p]
            body = r"[\s\-.]*".join(parts)
            pat = re.compile(rf"(?<![{_LETTER}]){body}(?![{_LETTER}])")
            out.append((pat, canonical, len(v)))
    out.sort(key=lambda x: -x[2])  # longest variant first ("Purva Phalguni" before "Phalguni")
    return out


_NAKSHATRA_PATTERNS = _compile(NAKSHATRAS)
_RASHI_PATTERNS = _compile(RASHIS)
_TITHI_PATTERNS = _compile(TITHIS)
_PAKSHA_PATTERNS = _compile(PAKSHAS)
_AYANAMSHA_PATTERNS = _compile(AYANAMSHAS)


def _find(patterns: list[tuple[re.Pattern[str], str, int]], text: str) -> tuple[str, int, int] | None:
    folded = _fold(text)
    best: tuple[str, int, int] | None = None
    for pat, canonical, _n in patterns:
        m = pat.search(folded)
        if m and (best is None or m.start() < best[1] or (m.start() == best[1] and m.end() > best[2])):
            best = (canonical, m.start(), m.end())
    return best


def find_nakshatra(text: str) -> str | None:
    hit = _find(_NAKSHATRA_PATTERNS, text)
    return hit[0] if hit else None


def find_rashi(text: str) -> str | None:
    hit = _find(_RASHI_PATTERNS, text)
    return hit[0] if hit else None


def find_tithi(text: str) -> str | None:
    hit = _find(_TITHI_PATTERNS, text)
    return hit[0] if hit else None


def find_paksha(text: str) -> str | None:
    hit = _find(_PAKSHA_PATTERNS, text)
    return hit[0] if hit else None


def find_ayanamsha(text: str) -> str | None:
    hit = _find(_AYANAMSHA_PATTERNS, text)
    return hit[0] if hit else None


def _exact(patterns: list[tuple[re.Pattern[str], str, int]], value: str) -> str | None:
    """Canonical name if the WHOLE value is one vocabulary entry (after trimming)."""
    v = _fold(value.strip())
    for pat, canonical, _n in patterns:
        m = pat.fullmatch(v)
        if m:
            return canonical
    return None


def canonical_nakshatra(value: str) -> str | None:
    return _exact(_NAKSHATRA_PATTERNS, value)


def canonical_rashi(value: str) -> str | None:
    return _exact(_RASHI_PATTERNS, value)


def canonical_tithi(value: str) -> str | None:
    return _exact(_TITHI_PATTERNS, value)


def canonical_paksha(value: str) -> str | None:
    return _exact(_PAKSHA_PATTERNS, value)


def canonical_ayanamsha(value: str) -> str | None:
    return _exact(_AYANAMSHA_PATTERNS, value)
