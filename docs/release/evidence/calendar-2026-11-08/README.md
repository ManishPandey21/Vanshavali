# Family calendar evidence, 8 Nov 2026 (ADR-0022)

Prepared by the development team for the licensing reviewer and the independent panchang reviewer.
**Nothing here is an approval.**

| File | What it is |
|---|---|
| `rashtriya-panchang-1948-pages.sha256` | SHA-256 of the Rashtriya Panchang 1948 Saka pages saved from `https://packolkata.imd.gov.in/panchang/en/` at 2026-11-08T12:20Z. These are the 12 month pages, the sunrise tables and the Explanation. The pages themselves are not committed: they are © Government of India, and permission to reproduce them is open item A-2. |
| `jpl-pages.sha256` | SHA-256 of the JPL Solar System Dynamics FAQ page quoted in the licence evidence. |
| `check-golden-amanta-{mumbai,delhi,chennai,kolkata}.txt` | `python -m app.cli.calendar check-golden --convention amanta --city …` against the transcribed table, with engine `skyfield-1.55/jplephem-2.24/de440s/lahiri-iau2006/1`. This is the developer's comparison, **not** independent verification. |
| `pac-pages.sha256` | SHA-256 of the PAC archive page and the PAC Disclaimer page as read on 2026-11-08. |
| `pac-english-editions-zip.sha256`, `pac-english-editions-pdf.sha256` | SHA-256 of the five English editions (2022-23 to 2026-27) downloaded from the PAC archive on 2026-11-08, and of the PDF inside each ZIP. The files are not committed. |
| `check-golden-amanta-mumbai-three-editions.txt` | Local evaluation of 2023-24 (PDF), 2025-26 (PDF) and 2026-27 (web) together at Mumbai. The transcribed values behind it are **not committed** (A-2). |
| `approval-template-amanta-mumbai.json` | The digests an accuracy approval for amanta × Mumbai would carry today. It goes stale when the engine, ephemeris, calculation code, convention, city or table changes. |

See `docs/operations/family-calendar-sources.md`, `family-calendar-licence-review.md` and
`family-calendar-approvals.md`.
