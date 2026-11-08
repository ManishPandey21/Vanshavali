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
| S-2 | Rashtriya Panchang, **earlier editions** (at least two more years; one of 1945 Saka, 2023–24, which has Adhik Shravana, is useful) | As S-1, for more years | **Not obtained.** Only the current edition is online. Order printed editions from IMD (Mausam Bhavan, Lodi Road, New Delhi 110003) or PAC (Salt Lake, Sector V, Kolkata 700091), or ask PAC for the digital tables. | Same as S-1 | Needed for the 3-year coverage rule |
| S-3 | Rashtriya Panchang, **1949 Saka Era (2027–28)** when published | As S-1 | Not yet published at retrieval | Same as S-1 | Optional; extends coverage |
| S-4 | **Indian Astronomical Ephemeris 2027** (PAC), `https://packolkata.imd.gov.in/download/IAE2027.zip` (linked from IMD) | Precise positions of Sun and Moon; the basis of the Rashtriya Panchang ("Explanation") | Not downloaded | Not checked | Optional cross-check |
| S-5 | **Supplementary: purnimanta month naming** (e.g. a published North-Indian panchang that names months the purnimanta way) | Which month a krishna-paksha tithi belongs to under purnimanta | **Not identified** | To be verified before use | Needed before purnimanta is validated anywhere |
| S-6 | **Supplementary: observance rules** (which civil day a Punyatithi/Shraddha is kept under the aparahna rule, and a birthday by tithi under the sunrise rule; vriddhi/kshaya cases; adhik months) for the convention and region | Published observance days to compare with `observance.occurrences` | **Not identified.** The Rashtriya Panchang lists festivals, not family observances. Candidates must be published panchangs or dharmashastra-based guides a panchang reviewer accepts. | To be verified before use | Needed: the checker reports these as coverage gaps |

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
| D-1 | Amavasya ending 2026-12-09 06:22 IST (printed on 8 Dec 2026, page "agrahayana") | "(Margasirsa Krishna) Amavasya h. 30-22" | Kartika (as the engine names it) | The same table prints the preceding tithi as "(Kartika Krishna) Chaturdasi" and the next as "(Margasirsa Sukla) Pratipad"; the edition's own rule reckons months from the day after the new moon; the edition's other 11 Amavasyas carry their Chaturdasi's month | **Pending**: a panchang reviewer decides (ideally against the printed edition or PAC errata). Recorded in `amanta.json` → `divergences`; the source row is kept as printed and the mismatch keeps counting until a named reviewer accepts it. |

## 5. Recommended first validation scope

The owner asked to validate **one city and one convention first**. Recommendation:
**amanta at Mumbai**.
- Amanta is the convention the primary source states directly.
- Mumbai's sunrise is published in the same edition.
- Maharashtra follows the amanta system (`data/conventions.json` lists MH under amanta).

Delhi, Chennai and Kolkata can follow on the same source. Purnimanta (for example Delhi or
Varanasi) waits for S-5. The choice is the product owner's.
