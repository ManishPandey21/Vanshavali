# Golden panchang tables (ADR-0022 §9)

One JSON file per convention (`amanta.json`, later `purnimanta.json`). **Rows are facts transcribed
from published panchangs, each citing its source; never values computed by the engine under
test.** A table is evidence for an independent reviewer. On its own it enables nothing: computed
lunar dates need the signed approvals in `../data/approvals.json` (see
`docs/operations/family-calendar-approvals.md`), and those approvals are bound to this file's
SHA-256, so editing a table makes them stale. They are also bound to the engine and ephemeris, the
calculation source code, the convention's rules and the city's coordinates.

Printed editions (PDF) are transcribed with `python -m app.cli.calendar transcribe-rp-pdf`. It
reports skipped rows and any `ANOMALY` (a row the edition's own calendar rule rules out), and never
fills a gap.

## What ships

| File | Source | Status |
|---|---|---|
| `amanta.json` | Rashtriya Panchang, 1948 Saka Era (2026–27), official online edition (IMD / Positional Astronomy Centre) | Draft: transcribed by `python -m app.cli.calendar transcribe-rp`; permission to reproduce **not yet verified**; **not independently reviewed**; one documented divergence pending |

## Format 2

```json
{
  "format": 2,
  "convention": "amanta",
  "status": "draft: …",
  "sources": {
    "<source key>": {
      "publisher": "…", "title": "…", "edition": "…", "url": "…", "retrieved": "…",
      "pages": {"<saved page>": "<sha256>"},        // or "pages_cited" for a printed edition
      "usage": "the copyright notice and whether permission is verified",
      "method": "how the rows were transcribed"
    }
  },
  "tithi_ends": [
    {"source": "…", "page": "kartika", "day": "2026-10-23", "printed": "(Asvina Sukla) Dvadasi h. 14-36",
     "ist": "2026-10-23T14:36", "month_convention": "amanta", "masa": "ashvin", "adhik": false,
     "paksha": "shukla", "tithi": 12}
  ],
  "sunrises": [{"source": "…", "page": "tables", "city": "mumbai", "date": "2026-03-22", "ist": "06:41"}],
  "observances": [{"source": "…", "city": "…", "kind": "memorial", "lunar": {…}, "date": "YYYY-MM-DD"}],
  "divergences": [{"row": {"ist": "…", "paksha": "…", "tithi": 0}, "field": "masa", "source_says": "…",
                   "other_reading": "…", "evidence": "…", "status": "pending: …", "accepted_by": null}]
}
```

- **Tithi endings** are geocentric moments in IST (Rashtriya Panchang, "Explanation"), so they
  hold for every city. Tolerance: 2 minutes.
- **Sunrise** is the published time for a city, to the minute. Tolerance: 90 seconds (the source's
  rounding plus up to a minute for its definition of sunrise: upper limb, 31′ refraction).
- **Civil days**: the tithi current at the city's published sunrise, derived from the source alone,
  must equal the engine's exactly. Days where a tithi ends within a minute of sunrise are counted as
  undecidable, not compared.
- **Divergences**: the source row is never edited. A divergence stops counting as a mismatch only
  when a named reviewer accepts it.

Coverage per convention and city (`golden_check.coverage_gaps`): sources with publisher, edition,
retrieval, pages and usage; at least 3 years of tithi endings; an adhik month; a day with no tithi
ending (vriddhi) and one with two (kshaya) at the city; the city's published sunrise; months named
the convention's way; and published observances for the memorial and birthday day rules.

```bash
uv run python -m app.cli.calendar check-golden --convention amanta --city mumbai
```
