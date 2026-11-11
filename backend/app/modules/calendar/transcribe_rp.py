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

import calendar
import datetime as dt
import hashlib
import html
import re
import shutil
import subprocess
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
    "Sravana": "shravana",  # the printed editions' spelling
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
# Spellings found in the printed editions, mapped to the names above. The printed text is kept on
# every row, so a reviewer sees the original. Anything not listed stops the transcription.
SPELLING_VARIANTS = {"Chaturti": "Chaturthi"}
# The metropolitan cities of the sunrise table, in its column order -> our city keys
METROS = ("chennai", "delhi", "kolkata", "mumbai")
JD_ORDINAL_OFFSET = 1721424.5  # JD at 0h UT (05:30 IST) of a date = its proleptic ordinal + this


class TranscriptionError(ValueError):
    pass


def national_month_starts(saka_year: int) -> list[dt.date]:
    """The first Gregorian day of each National Calendar month of ``saka_year``, and of the next Chaitra.

    The rule is the one the edition's "Explanation" states: Chaitra 1 is 22 March, or 21 March when
    the Gregorian year (Saka + 78) is a leap year; Chaitra has 30 days (31 in a leap year), Vaisakha
    to Bhadra 31, Asvina to Phalguna 30. Every sunrise row is checked against its printed day.
    """
    year = saka_year + 78
    leap = calendar.isleap(year)
    starts = [dt.date(year, 3, 21 if leap else 22)]
    for days in [31 if leap else 30, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 30]:
        starts.append(starts[-1] + dt.timedelta(days=days))
    return starts


def _text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def _tithi_items(text: str) -> list[dict[str, Any]]:
    """'(Mala Jyaishtha Krishna) Amavasya h. 8-24 then (Shuddha Jyaishtha Sukla) Pratipad h. 28-31'."""
    items = []
    label: tuple[str, str, bool] | None = None
    for part in text.split(" then "):
        m = re.fullmatch(
            r"(?:\((?:(?P<adj>Mala |Shuddha |Suddha )?(?P<masa>\w+) )?(?P<paksha>Sukla|Krishna)\) )?(?P<name>\w+) "
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
        name = SPELLING_VARIANTS.get(m["name"], m["name"])
        if label is None or name not in TITHI:
            raise TranscriptionError(f"cannot read {part!r} in {text!r}")
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
    starts = national_month_starts(1948)
    if len(tables) != len(starts):
        raise TranscriptionError(f"expected {len(starts)} sunrise tables, found {len(tables)}")
    rows = []
    for start, table in zip(starts, tables, strict=True):
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


# ---------------------------------------------------------------- printed editions (PDF)
_GREGORIAN = "January|February|March|April|May|June|July|August|September|October|November|December"
SUNRISE_HEADER = "Sunrise, Sunset & Moonrise, Moonset at four metropolitan cities"


def pdf_text(pdf: Path) -> str:
    """The PDF's text with its layout kept (poppler's ``pdftotext -layout``); pages split by form feed."""
    exe = shutil.which("pdftotext")
    if exe is None:
        raise TranscriptionError("pdftotext (poppler-utils) is needed to read a printed edition")
    # a fixed argument list, no shell: the PDF path is passed as one argument
    done = subprocess.run([exe, "-layout", str(pdf), "-"], check=True, capture_output=True, timeout=600)  # noqa: S603
    return done.stdout.decode("utf-8")


def _normalise(segment: str) -> str:
    text = re.sub(r"\s+", " ", segment).strip()
    text = re.sub(r"\(\s+", "(", text)
    return re.sub(r"\)(?=\S)", ") ", text)


def pdf_tithi_rows(text: str, source: str, page_label: str) -> list[dict[str, Any]]:
    days = list(re.finditer(r"Julian Day:\s*(\d+\.5)(?!\s*-)", text))
    if not days:
        raise TranscriptionError("no daily panchang found")
    rows = []
    for k, jd in enumerate(days):
        date = dt.date.fromordinal(int(float(jd.group(1)) - JD_ORDINAL_OFFSET))
        printed = re.findall(rf"(\d{{1,2}}) ?({_GREGORIAN}),", text[max(0, jd.start() - 400) : jd.start()])
        if not printed or (int(printed[-1][0]), printed[-1][1]) != (date.day, date.strftime("%B")):
            raise TranscriptionError(
                f"Julian Day {jd.group(1)} does not match the printed date {printed[-1:]}"
            )
        end = days[k + 1].start() if k + 1 < len(days) else len(text)
        segment = re.search(r"Tithi:(.*?)Nakshatra:", text[jd.end() : end], flags=re.S)
        if not segment:
            raise TranscriptionError(f"no tithi for {date}")
        for item in _tithi_items(_normalise(segment.group(1))):
            if item["end"] is None:
                continue
            h, m = item["end"]
            moment = dt.datetime.combine(date, dt.time()) + dt.timedelta(hours=h, minutes=m)
            rows.append(
                {
                    "source": source,
                    "page": page_label,
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


def pdf_sunrise_rows(
    text: str, source: str, page_label: str, saka_year: int, wanted: set[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Metro sunrises from the tables at the end of the edition. A row that does not have exactly the
    35 numbers of a full row (a moonrise or moonset left blank shifts the columns) is skipped and
    reported, never guessed."""
    # 13 months (Chaitra to the next Chaitra) and the day after the last one
    starts = national_month_starts(saka_year) + national_month_starts(saka_year + 1)[1:2]
    rows: list[dict[str, Any]] = []
    skipped: list[str] = []
    table, n = -1, 0
    for page in text.split("\f"):
        if SUNRISE_HEADER not in page:
            continue
        for line in page.splitlines():
            nums = re.findall(r"\d+", line)
            if len(nums) < 11 or not line.strip()[:1].isdigit():
                continue  # headers ("1945 5123 2023 Sun Moon …") and blank lines
            if int(nums[0]) == 1:
                table, n = table + 1, 0
            n += 1
            if table < 0 or table >= len(starts) - 1 or int(nums[0]) != n:
                raise TranscriptionError(f"sunrise table out of order at {line.strip()!r}")
            date = starts[table] + dt.timedelta(days=n - 1)
            if date >= starts[table + 1]:
                # a row beyond the month's length under the edition's own calendar rule: kept as an
                # anomaly for the reviewer, never used
                skipped.append(
                    f"ANOMALY after {starts[table + 1] - dt.timedelta(days=1)}: {' '.join(nums[:7])} …"
                )
                continue
            if len(nums) != 35:
                skipped.append(f"{date}: {len(nums)} numbers")
                continue
            times = list(zip(nums[3::2], nums[4::2], strict=True))
            if not all(len(m) == 2 and int(m) < 60 and len(h) <= 2 and int(h) <= 31 for h, m in times):
                # the text layer split or merged digits ("6 0 5 1 8 2 0" for "6 05 18 20")
                skipped.append(f"{date}: malformed times")
                continue
            if int(nums[2]) != date.day:
                raise TranscriptionError(f"sunrise row {line.strip()!r} does not follow {date}")
            for i, city in enumerate(METROS):
                if city in wanted:
                    hh, mm = int(nums[3 + 8 * i]), int(nums[4 + 8 * i])
                    rows.append(
                        {
                            "source": source,
                            "page": page_label,
                            "city": city,
                            "date": date.isoformat(),
                            "ist": f"{hh:02d}:{mm:02d}",
                        }
                    )
    return rows, skipped


def transcribe_pdf(
    pdf: Path, archive_sha256: str, saka_year: int, url: str, retrieved: str, cities: set[str]
) -> dict[str, Any]:
    source = f"rashtriya-panchang-{saka_year}-pdf"
    text = pdf_text(pdf)
    ends = sorted(pdf_tithi_rows(text, source, pdf.name), key=lambda r: r["ist"])
    rises, skipped = pdf_sunrise_rows(text, source, pdf.name, saka_year, cities)
    first, last = saka_year + 78, saka_year + 79
    return {
        "format": 2,
        "convention": "amanta",
        "status": "draft: transcribed, not independently reviewed; no approval",
        "sources": {
            source: {
                "publisher": PUBLISHER,
                "title": f"Rashtriya Panchang, {saka_year} Saka Era ({first}-{str(last)[2:]} A.D.)",
                "edition": "official English edition, PDF distributed by PAC",
                "url": url,
                "retrieved": retrieved,
                "pages": {
                    url.rsplit("/", 1)[-1]: archive_sha256,
                    pdf.name: hashlib.sha256(pdf.read_bytes()).hexdigest(),
                },
                "usage": (
                    "Published by the Government of India (IMD/PAC); the PAC website shows no licence for "
                    "reuse. Permission to reproduce transcribed values is NOT yet verified."
                ),
                "method": (
                    "Text extracted with poppler 'pdftotext -layout' and transcribed by "
                    "app.modules.calendar.transcribe_rp; dates from each day's printed Julian Day, checked "
                    "against the printed date. No value was computed by the engine under test."
                ),
                "skipped_sunrise_rows": skipped,
            }
        },
        "tithi_ends": ends,
        "sunrises": rises,
        "observances": [],
        "divergences": [],
    }
