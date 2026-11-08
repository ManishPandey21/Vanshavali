# Family calendar evidence, 8 Nov 2026 (ADR-0022)

Prepared by the development team for the licensing reviewer and the independent panchang reviewer.
**Nothing here is an approval.**

| File | What it is |
|---|---|
| `rashtriya-panchang-1948-pages.sha256` | SHA-256 of the Rashtriya Panchang 1948 Saka pages saved from `https://packolkata.imd.gov.in/panchang/en/` at 2026-11-08T12:20Z. These are the 12 month pages, the sunrise tables and the Explanation. The pages themselves are not committed: they are © Government of India, and permission to reproduce them is open item A-2. |
| `jpl-pages.sha256` | SHA-256 of the JPL Solar System Dynamics FAQ page quoted in the licence evidence. |
| `check-golden-amanta-{mumbai,delhi,chennai,kolkata}.txt` | `python -m app.cli.calendar check-golden --convention amanta --city …` against the transcribed table, with engine `skyfield-1.55/jplephem-2.24/de440s/lahiri-iau2006/1`. This is the developer's comparison, **not** independent verification. |
| `approval-template-amanta-mumbai.json` | The digests an accuracy approval for amanta × Mumbai would carry today. It goes stale when the table, the convention, the engine or the ephemeris changes. |

See `docs/operations/family-calendar-sources.md`, `family-calendar-licence-review.md` and
`family-calendar-approvals.md`.
