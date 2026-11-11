# Family calendar: panchang source and reference inventory (ADR-0022 §9)

Product owner's decision of 8 Nov 2026: the **Rashtriya Panchang** (Government of India, published
by the India Meteorological Department through the Positional Astronomy Centre, Kolkata) is the
primary astronomical reference. Supplementary published sources are needed for the amanta and
purnimanta conventions and regional observance rules, each with its usage permission verified.
Golden data is transcribed and source-attributed by the development team and reviewed
independently; expected values are never invented, and sanity checks are not verification.

## 1. Sources

| # | Source | What it gives | Obtained | Usage permission | Status |
|---|---|---|---|---|---|
| S-1 | **Rashtriya Panchang, 1948 Saka Era (2026–27 A.D.)**, official online edition, English, `https://packolkata.imd.gov.in/panchang/en/` (linked from `https://mausam.imd.gov.in/responsive/rashtriyPanchang.php`) | Daily tithi with its **ending moment in IST** and the lunar month in the **amanta** system ("Mala"/"Shuddha" for adhik/nija); daily sunrise and sunset for **Chennai, Delhi, Kolkata, Mumbai**; sunrise for the adopted Central Station (82°30′E, 23°11′N); method notes ("Explanation") | 12 month pages and the sunrise tables saved on 2026-11-08T12:20Z; page checksums in `docs/release/evidence/calendar-2026-11-08/rashtriya-panchang-1948-pages.sha256`; transcribed into `backend/app/modules/calendar/golden/amanta.json` (371 tithi endings, 22 Mar 2026 – 21 Mar 2027; 1,580 city sunrises) | Site footer: "© Government of India \| All Rights Reserved". **Permission to reproduce the transcribed values in this repository is not verified** (licence review item L-6). The site says copies are available from IMD, New Delhi and PAC, Kolkata. | Transcribed; not independently reviewed |
| S-2 | **Rashtriya Panchang, English editions 2022-23 to 2026-27 (1944–1948 SE)**, PDF, from the PAC archive page `rashtriya-panchang-english.php` (owner's link `https://www.packolkata.gov.in/…`; read here as `https://packolkata.imd.gov.in/rashtriya-panchang-english.php`, the same server, see §6) | As S-1, for each Saka year, including the 13th month (the next Chaitra) | **All five downloaded** 2026-11-08T13:0xZ over verified HTTPS: `https://packolkata.imd.gov.in/download/EnglishRP{2223,2324,2425,2526,2627}.zip`, each one PDF (193–198 pages, text layer present, not scans). ZIP and PDF SHA-256 in `docs/release/evidence/calendar-2026-11-08/pac-english-editions-*.sha256`. 2023-24 and 2025-26 assessed in §6; **their transcribed values are not committed** (A-2). | No licence on the page; the PAC **Disclaimer** (`/disclaimer.php`) says PAC "makes no warranties … Nor this Centre warrants that use of works is free from any claims of copyright infringement". The printed editions carry a price (Rs. 225.00) and, in their text layer, no copyright or licence statement. **Not verified** (A-2). | 2023-24 and 2025-26: **suitable**, with the limitations in §6 |
| S-3 | Rashtriya Panchang, **1949 Saka Era (2027–28)** when published | As S-1 | Not yet published at retrieval | Same as S-1 | Optional; extends coverage |
| S-4 | **Indian Astronomical Ephemeris 2027** (PAC), `https://packolkata.imd.gov.in/download/IAE2027.zip` (linked from IMD) | Precise positions of Sun and Moon; the basis of the Rashtriya Panchang ("Explanation") | Not downloaded | Not checked | Optional cross-check |
| S-5 | **Supplementary: purnimanta month naming** (e.g. a published North-Indian panchang that names months the purnimanta way) | Which month a krishna-paksha tithi belongs to under purnimanta | **Not identified** | To be verified before use | Needed before purnimanta is validated anywhere |
| S-6 | **Supplementary: observance rules** (which civil day a Punyatithi/Shraddha is kept under the aparahna rule, and a birthday by tithi under the sunrise rule; vriddhi, kshaya and adhik cases) | Published observance days or rules to compare with `observance.occurrences` | **Candidates identified, none verified as an operational source**: see §7 | See §7 | Needed: the checker reports these as coverage gaps |

## 2. What the primary source settles, and what it does not

From the edition's "Explanation" page (retrieved 2026-11-08):

- Tithi ending moments are **geocentric, in IST, valid for every place in the country**; "reduced
  by 5h 30m [they] would give the UT … applicable for all places on the earth". So the engine's
  tithi moments can be checked for any city, including the overseas ones.
- Months are **amanta** ("reckoned from the day following the new moon … named after the nirayana
  solar month in which this initial new moon falls"). The primary source therefore checks the
  **amanta** convention directly; purnimanta month names need S-5.
- Sunrise and sunset are for the **upper limb, with 31′ horizontal refraction and 16′
  semi-diameter**, in IST, for the four metropolitan cities (and the Central Station). The engine
  uses Skyfield's standard sunrise; the observed difference is at most 56 s (below).
- The Rashtriya Panchang assigns a tithi to a day by the **Central Station's** sunrise. A family's
  observance uses **its own city's** sunrise; the checker derives the tithi at each city's published
  sunrise from the source's own tithi endings, so no engine value enters the expectation.

## 3. Developer comparison (not verification)

`python -m app.cli.calendar check-golden --convention amanta --city <city>` against S-1, 8 Nov 2026
(full output in `docs/release/evidence/calendar-2026-11-08/`):

| City | Tithi endings compared | Largest difference | Sunrises compared | Largest difference | Civil days (tithi at sunrise) | Mismatches |
|---|---|---|---|---|---|---|
| Mumbai | 371 | 36 s | 395 | 56 s | 363 equal, 1 undecidable | 1 (D-1) |
| Delhi | 371 | 36 s | 395 | 44 s | 363 equal, 1 undecidable | 1 (D-1) |
| Chennai | 371 | 36 s | 395 | 53 s | 363 equal, 1 undecidable | 1 (D-1) |
| Kolkata | 371 | 36 s | 395 | 53 s | 364 equal | 1 (D-1) |

This is the development team's own check against an official source. It is **not** the
independent review the owner requires, and no convention passes: coverage is one year (three are
required) and the observance rules are unchecked.

## 4. Divergences found

| # | Where | The source says | Other reading | Evidence | Status |
|---|---|---|---|---|---|
| D-1 | Amavasya ending 2026-12-09 06:22 IST (printed on 8 Dec 2026, page "agrahayana") | "(Margasirsa Krishna) Amavasya h. 30-22" | Kartika (as the engine names it) | The same table prints the preceding tithi as "(Kartika Krishna) Chaturdasi" and the next as "(Margasirsa Sukla) Pratipad"; the edition's own rule reckons months from the day after the new moon; the edition's other 11 Amavasyas carry their Chaturdasi's month | **Pending**: PAC's clarification or the independent reviewer's decision (A-6). **The official PDF of the same edition prints the same text** ("(Margasirsa Krishna) Amavasya h. 30-22"), so it is not a transcription or website error. Recorded in `amanta.json` → `divergences`; the source row is kept as printed and the mismatch keeps counting until a named reviewer accepts it. |
| D-2 | Sunrise table for Chaitra 1948 SE (2026) at the end of the **2025-26 (1947 SE) PDF** | a 31st row "31 8 20 5 54 18 22 …" | Chaitra 1948 has 30 days (the edition's own rule); the row repeats, number for number apart from the day numbers, the 2025 table's day-30 row, and its Gregorian day (20) repeats the row before it | Found while transcribing; the 2026-27 edition's own Chaitra table has 30 rows | **Recorded, not used**: the transcriber keeps it as an `ANOMALY` and skips it. To report to PAC with D-1. |

## 5. Recommended first validation scope

The owner asked to validate **one city and one convention first**. Recommendation:
**amanta at Mumbai**.
- Amanta is the convention the primary source states directly.
- Mumbai's sunrise is published in the same edition.
- Maharashtra follows the amanta system (`data/conventions.json` lists MH under amanta).

Delhi, Chennai and Kolkata can follow on the same source. Purnimanta (for example Delhi or
Varanasi) waits for S-5. The choice is the product owner's.

## 6. Archive editions 2023-24 and 2025-26: access and suitability (8 Nov 2026)

**Access.** The owner's link `https://www.packolkata.gov.in/rashtriya-panchang-english.php`
failed TLS verification from this environment: through the session's network proxy the server
presented its `*.imd.gov.in` certificate. A direct TLS connection showed a valid
`*.packolkata.gov.in` certificate (to 8 Dec 2026), so the cause is the path through the proxy, not
the site. Verification was not bypassed. The same page and files were read over verified HTTPS at
`packolkata.imd.gov.in`, which is the same server (same IP address). The plain-HTTP copy of the
page lists the same five editions, and was used only for that comparison.

| Edition | File | Pages | Daily entries | Tithi endings transcribed | Mumbai sunrises usable | Notes |
|---|---|---|---|---|---|---|
| 2023-24, 1945 SE | `EnglishRP2324.zip` → `RP_1945SE.pdf` | 193 | 396 | 402 (22 Mar 2023 – 20 Apr 2024) | 352 | Adhik **Mala/Suddha Sravana** 2023 (30 rows); 44 sunrise rows skipped (blank moonrise or moonset cells, or split digits) |
| 2025-26, 1947 SE | `EnglishRP2526.zip` → `RP 1947 SE English Final.pdf` | 197 | 395 | 402 (23 Mar 2025 – 21 Apr 2026) | 366 | No adhik month; 30 rows skipped, one of them anomaly **D-2** |
| 2026-27, 1948 SE (PDF of S-1) | `EnglishRP2627.zip` → `RP 1948 SE Final.pdf` | 193 | 395 | 402 | 366 | 29 rows skipped; used only to check the PDF method against the web edition |

**How the PDFs were read.**
- Text comes from poppler `pdftotext -layout` and is parsed by `app.cli.calendar transcribe-rp-pdf`.
- Each date comes from the day's printed Julian Day, checked against the printed date.
- Sunrise rows use the national-calendar rule stated in the edition's Explanation and are checked
  against each row's printed Gregorian day.
- A row is used only if it has all 35 numbers and well-formed times; anything else is skipped and
  listed.
- Known printed spellings are mapped and listed in the code: "Sravana", "Suddha", "( Mala", and
  "Chaturti" (once, for Chaturthi). Every row keeps its printed text.

**Checks of the method.**
- The 2026-27 PDF agrees with the independently transcribed web edition on all 371 tithi endings,
  including month names, and on all 1,464 sunrises the two have in common.
- The 2025-26 edition's 13th month agrees with the 2026-27 edition on all 31 shared tithi endings
  and all 112 shared sunrises.

**Suitability for the 3-year rule (amanta × Mumbai).** This is the development team's local
comparison, not verification; full output is in
`docs/release/evidence/calendar-2026-11-08/check-golden-amanta-mumbai-three-editions.txt`. The
2023-24 PDF, 2025-26 PDF and 2026-27 web editions were compared together:
- 1,144 tithi endings, all within 39 s;
- 1,085 Mumbai sunrises, all within 56 s;
- 1,052 civil days equal and 2 undecidable;
- no mismatch other than **D-1**.

Coverage then meets the 3-year and adhik requirements. What remains open is the observance rules
(S-6) and the reviews.

**Limitations.**
1. **The years are not continuous.** 2024-25 (1946 SE) is not used: the owner named 2023-24 and
   2025-26. It is available (`EnglishRP2425.zip`) if the reviewer wants continuity.
2. **Mumbai sunrise is missing on some days.** About 3–4 % of rows can't be read safely because of
   blank cells or split digits in the text layer. Those days have no published Mumbai sunrise in
   the table, and no value was filled in.
3. **The values are transcribed, not typed by a person.** The reviewer's spot check (checklist)
   applies.
4. **Copyright status is open (A-2).** Until it is resolved, the 2023-24 and 2025-26 values are
   **not committed**: only checksums and the comparison output are. Adding them is one command per
   edition once permitted.
5. **Same publisher.** All editions come from PAC, so they are consistent with each other but not
   independent of each other.

## 7. Observance-rule sources (S-6): what was found

Nothing below is yet accepted as an operational source. The panchang reviewer decides which
texts, and which community's practice, apply.

| Candidate | What it covers | Checked here | Usage |
|---|---|---|---|
| P. V. Kane, *History of Dharmaśāstra*, Vol. IV (BORI, Poona, 1953), Śrāddha section; scan at `archive.org/details/HistoryOfDharmasastraancientAndMediaevalReligiousAndCivilLawV.4` | Annual śrāddha (pratyābdika/pratisāṃvatsarika) | **Read in the scan's text layer** (around p. 530, page number unclear in the OCR). The annual śrāddha is performed on the day of death; "the month in pitrya rites is lunar" and day words "mean 'tithi'" (citing Aparārka p. 545); there are fallbacks when the month or tithi is unknown; and "There is no pratyābdika śrāddha in an intercalary month" (citing Skanda VII.1.206.59). The **two-day (viddha) decision was not found** in the passages read. | Kane died in 1972. Whether the work is still in copyright in India, and what may be quoted, is for the licensing reviewer. Rules are cited, not reproduced. |
| Kane, *History of Dharmaśāstra*, Vol. V (kāla: tithis, viddha tithis) | Choice of day when a tithi spans two days, festivals | **Not checked** | As above |
| *Nirṇayasindhu* (Kamalākara Bhaṭṭa, 17th c.) and *Dharmasindhu* (Kāśīnātha Upādhyāya, 18th c.) | The digests on deciding the day of a tithi (tithi-nirṇaya), including aparāhṇa-vyāpinī śrāddha and udaya (sunrise) tithi | **Not checked against an edition.** Only secondary web pages were found, and they disagree on the tie rule (more aparāhṇa coverage vs the first day). | The Sanskrit texts are old; modern editions and translations have their own rights. Edition to be chosen and checked. |
| Kāñcī Kāmakoṭi Pīṭham, *Essence of Dharma Sindhu* (English, kamakoti.org, ch. 6) | English rendering | Read chapter 6: it gives **different rules for different Vedic communities** (Taittirīya and other Yajurvedins) and records "different opinions" by the ghaṭīs a tithi extends. No janma-tithi passage was found there (a search summary claiming one was not confirmed). | © 2000-2026 Shri Kanchi Kamakoti Peetham; reuse not permitted without verification |

**Regional and community differences recorded so far.**
- Day rules differ by community (śākhā), not only by region (Dharmasindhu rendering above).
- Secondary sources disagree on ties under the aparāhṇa rule.
- Kane records no annual śrāddha in an adhik month. This matches the engine's nija rule for an
  ordinary anchor. What applies to a death that **occurred** in an adhik month (the engine uses the
  adhik month when the year has one) is **unverified** and is for the reviewer.

**Birthdays by tithi (sunrise rule):** no published source has been verified yet.

