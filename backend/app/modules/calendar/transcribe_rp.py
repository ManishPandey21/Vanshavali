"""Transcribe the official online Rashtriya Panchang into a golden table (format 2).

Input: pages of https://packolkata.imd.gov.in/panchang/en/ saved by an operator (the twelve month
pages and ``tables``), with a ``SHA256SUMS`` file and a ``RETRIEVED`` timestamp. Output: the
facts as published, each row naming its page, and the source record with every page's checksum.

**Nothing here computes an astronomical value.** It copies times and names, converts the
published "h. 26-38" notation (hours past the civil day's midnight, IST) to a timestamp, and
derives Gregorian dates only from the Julian Day the page prints for that day (checked against
the printed date). Anything unexpected stops the transcription rather than being guessed.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import re
from pathlib import Path
from typing import Any

PUBLISHER = (
    "India Meteorological Department, Positional Astronomy Centre, Kolkata (Ministry of Earth Sciences)"
)
BASE_URL = "https://packolkata.imd.gov.in/panchang/en/"
MONTH_PAGES = (
    "chaitra",
    "vaishaka",
    "jyaishtha",
    "ashadha",
    "sravana",
    "bhadra",
    "asvina",
    "kartika",
    "agrahayana",
    "pausha",
    "magha",
    "phalguna",
)
# Lunar month names as the Rashtriya Panchang prints them -> app.core.lunar.MASAS keys
MASA = {
    "Chaitra": "chaitra",
    "Vaisakha": "vaishakha",
    "Jyaishtha": "jyeshtha",
    "Ashadha": "ashadha",
    "Shravana": "shravana",
    "Bhadra": "bhadrapada",
    "Asvina": "ashvin",
    "Kartika": "kartika",
    "Margasirsa": "margashirsha",
    "Pausha": "pausha",
    "Magha": "magha",
    "Phalguna": "phalguna",
}
PAKSHA = {"Sukla": "shukla", "Krishna": "krishna"}
TITHI = {
    "Pratipad": 1,
    "Dvitiya": 2,
    "Tritiya": 3,
    "Chaturthi": 4,
    "Panchami": 5,
    "Shashthi": 6,
    "Saptami": 7,
    "Ashtami": 8,
    "Navami": 9,
    "Dasami": 10,
    "Ekadasi": 11,
    "Dvadasi": 12,
    "Trayodasi": 13,
    "Chaturdasi": 14,
    "Purnima": 15,
    "Amavasya": 15,
}
# The metropolitan cities of the sunrise table, in its column order -> our city keys
METROS = ("chennai", "delhi", "kolkata", "mumbai")
# First Gregorian day of each National Calendar month of 1948-1949 Saka (the "Explanation" page's
# table; 2026 and 2027 are not leap years). Every sunrise row is checked against its printed day.
NATIONAL_MONTH_STARTS = (
    dt.date(2026, 3, 22),
    dt.date(2026, 4, 21),
    dt.date(2026, 5, 22),
    dt.date(2026, 6, 22),
    dt.date(2026, 7, 23),
    dt.date(2026, 8, 23),
    dt.date(2026, 9, 23),
    dt.date(2026, 10, 23),
    dt.date(2026, 11, 22),
    dt.date(2026, 12, 22),
    dt.date(2027, 1, 21),
    dt.date(2027, 2, 20),
    dt.date(2027, 3, 22),
)
JD_ORDINAL_OFFSET = 1721424.5  # JD at 0h UT (05:30 IST) of a date = its proleptic ordinal + this


class TranscriptionError(ValueError):
    pass


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _tithi_items(text: str) -> list[dict[str, Any]]:
    """'(Mala Jyaishtha Krishna) Amavasya h. 8-24 then (Shuddha Jyaishtha Sukla) Pratipad h. 28-31'."""
    items = []
    label: tuple[str, str, bool] | None = None
    for part in text.split(" then "):
        m = re.fullmatch(
            r"(?:\((?:(?P<adj>Mala |Shuddha )?(?P<masa>\w+) )?(?P<paksha>Sukla|Krishna)\) )?(?P<name>\w+) "
            r"(?:h\. (?P<h>\d{1,2})-(?P<m>\d{2})|(?P<aho>ahoratra))",
            part.strip(),
        )
        if not m:
            raise TranscriptionError(f"unexpected tithi text: {text!r}")
        if m["masa"]:
            if m["masa"] not in MASA:
                raise TranscriptionError(f"unknown month in {text!r}")
            label = (MASA[m["masa"]], PAKSHA[m["paksha"]], (m["adj"] or "").strip() == "Mala")
        elif m["paksha"]:
            # '(Krishna) Pratipad': the paksha turns within the same (amanta) month named earlier that day
            if label is None or label[1] != "shukla" or m["paksha"] != "Krishna":
                raise TranscriptionError(f"a paksha without its month in {text!r}")
            label = (label[0], "krishna", label[2])
        if label is None or m["name"] not in TITHI:
            raise TranscriptionError(f"cannot read {part!r} in {text!r}")
        name = m["name"]
        if (name == "Purnima" and label[1] != "shukla") or (name == "Amavasya" and label[1] != "krishna"):
            raise TranscriptionError(f"{name} in the wrong paksha: {text!r}")
        items.append(
            {
                "masa": label[0],
                "paksha": label[1],
                "adhik": label[2],
                "tithi": TITHI[name],
                "printed": part.strip(),
                "end": None if m["aho"] else (int(m["h"]), int(m["m"])),
            }
        )
    return items


def month_rows(page: str, source: str, content: str) -> list[dict[str, Any]]:
    days = list(re.finditer(r"<strong>Julian Day:</strong>\s*([\d.]+)\s*</p>", content))
    tithis = list(re.finditer(r"<strong>Tithi:</strong>(.*?)</p>", content, flags=re.S))
    if not tithis or not days:
        raise TranscriptionError(f"{page}: no daily panchang found")
    rows = []
    for t in tithis:
        jd_match = [d for d in days if d.start() < t.start()][-1]
        date = dt.date.fromordinal(int(float(jd_match.group(1)) - JD_ORDINAL_OFFSET))
        printed = re.search(
            r"(\d{1,2}) (January|February|March|April|May|June|July|August|September|October|November|December),",
            _text(content[jd_match.start() - 1500 : jd_match.start()]),
        )
        if not printed or (int(printed.group(1)), printed.group(2)) != (date.day, date.strftime("%B")):
            raise TranscriptionError(
                f"{page}: Julian Day {jd_match.group(1)} does not match the printed date"
            )
        for item in _tithi_items(_text(t.group(1))):
            if item["end"] is None:
                continue  # 'ahoratra': no tithi ends on this day
            h, m = item["end"]
            moment = dt.datetime.combine(date, dt.time()) + dt.timedelta(hours=h, minutes=m)
            rows.append(
                {
                    "source": source,
                    "page": page,
                    "day": date.isoformat(),
                    "printed": item["printed"],
                    "ist": moment.isoformat(timespec="minutes"),
                    "month_convention": "amanta",
                    "masa": item["masa"],
                    "adhik": item["adhik"],
                    "paksha": item["paksha"],
                    "tithi": item["tithi"],
                }
            )
    return rows


def sunrise_rows(source: str, content: str, wanted: set[str]) -> list[dict[str, Any]]:
    tables = re.findall(r"<table.*?</table>", content, flags=re.S)
    if len(tables) != len(NATIONAL_MONTH_STARTS):
        raise TranscriptionError(f"expected {len(NATIONAL_MONTH_STARTS)} sunrise tables, found {len(tables)}")
    rows = []
    for start, table in zip(NATIONAL_MONTH_STARTS, tables, strict=True):
        n = 0
        for tr in re.findall(r"<tr.*?</tr>", table, flags=re.S):
            cells = [_text(c) for c in re.findall(r"<t[hd][^>]*>(.*?)</t[hd]>", tr, flags=re.S)]
            if not cells or not cells[0].isdigit():
                continue
            if len(cells) != 19:
                raise TranscriptionError(f"sunrise row with {len(cells)} cells: {cells}")
            date = start + dt.timedelta(days=n)
            n += 1
            if int(cells[0]) != n or int(cells[2]) != date.day:
                raise TranscriptionError(f"sunrise row {cells[:3]} does not follow {date}")
            for i, city in enumerate(METROS):
                if city not in wanted:
                    continue
                hh, mm = cells[3 + 4 * i].split()
                rows.append(
                    {
                        "source": source,
                        "page": "tables",
                        "city": city,
                        "date": date.isoformat(),
                        "ist": f"{int(hh):02d}:{int(mm):02d}",
                    }
                )
    return rows


def transcribe(
    pages_dir: Path, cities: set[str], source: str = "rashtriya-panchang-1948-online"
) -> dict[str, Any]:
    sums = {}
    for line in (pages_dir / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split()
        sums[name] = digest
    retrieved = (pages_dir / "RETRIEVED").read_text().strip()

    def read(name: str) -> str:
        data = (pages_dir / f"{name}.html").read_bytes()
        if hashlib.sha256(data).hexdigest() != sums.get(f"{name}.html"):
            raise TranscriptionError(f"{name}.html does not match SHA256SUMS")
        return data.decode("utf-8")

    ends: list[dict[str, Any]] = []
    for page in MONTH_PAGES:
        ends += month_rows(page, source, read(page))
    ends.sort(key=lambda r: r["ist"])
    seen = set()
    for r in ends:
        key = (r["ist"], r["paksha"], r["tithi"])
        if key in seen:
            raise TranscriptionError(f"duplicate tithi ending {key}")
        seen.add(key)
    rises = sunrise_rows(source, read("tables"), cities)
    pages = {f"{p}.html": sums[f"{p}.html"] for p in (*MONTH_PAGES, "tables")}
    return {
        "format": 2,
        "convention": "amanta",
        "status": "draft: transcribed, not independently reviewed; no approval",
        "sources": {
            source: {
                "publisher": PUBLISHER,
                "title": "Rashtriya Panchang, 1948 Saka Era (2026-27 A.D.)",
                "edition": "official online edition, English",
                "url": BASE_URL,
                "retrieved": retrieved,
                "pages": pages,
                "usage": (
                    "Site footer: '(c) Government of India | All Rights Reserved'. Permission to "
                    "reproduce these transcribed values in this repository is NOT yet verified."
                ),
                "method": (
                    "Transcribed by app.modules.calendar.transcribe_rp from the saved pages; tithi ending "
                    "moments are IST and geocentric (valid for every place, per the edition's Explanation); "
                    "sunrise is the upper limb with 31' refraction, to the minute, for the four metropolitan "
                    "cities. No value was computed by the engine under test."
                ),
            }
        },
        "tithi_ends": ends,
        "sunrises": rises,
        "observances": [],
        "divergences": [],
    }
