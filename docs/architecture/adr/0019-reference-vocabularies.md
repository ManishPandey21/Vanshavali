# ADR-0019: Reference vocabularies in the database (typing aids for searchable fields)

- Status: Accepted · Date: 2026-10-06
- Relates to: ADR-0003 (no inference), ADR-0007 (search normalisation), ADR-0015 (places),
  ADR-0018 (kin-term quick-add)
- Design reference: [searchable-fields-catalogue.md](../searchable-fields-catalogue.md)

## Context
The searchable-fields catalogue lists about 25 fields that should suggest standard values as the
user types: gotra, kuladevata, religion, rashi, nakshatra, month in several calendars, country,
state, district, language, script, kin term, occupation and others. Today these suggestions come
from two places that have already drifted apart:

- hard-coded TypeScript lists in `frontend/src/data/masterData/*` (15 gotras, 8 kulas, rashis,
  nakshatras), and
- Python dictionaries in `backend/app/modules/astrology/vocab.py`, which validate and normalise
  rashi, nakshatra, tithi, paksha and ayanamsha values.

Some lists are too large or change too often to ship in the JavaScript bundle. India's district
list changes several times a year, and the LGD sub-district list has about 7,000 entries.

## Decision

### Two global tables, read-only to the application
- `vocabulary(code PK, name, description, parent_vocabulary_code → vocabulary, version, source,
  license, updated_at)`: one row per list (`gotra`, `state`, `district`, `kin_term`, …).
  `parent_vocabulary_code` declares a cascade, for example `district` → `state` → `country`,
  `sampradaya` → `religion`, and `month` → `calendar_system`.
- `vocabulary_term(id, vocabulary_code → vocabulary, code, parent_id → vocabulary_term, label,
  labels JSONB {lang: text}, aliases text[], tags text[], attributes JSONB, sort_order, is_active,
  search_text)`. Unique on `(vocabulary_code, code)`. Trigram GIN index on `search_text`.
  - `code` is stable and is what other records store. Labels can be renamed or translated without
    changing data.
  - `labels` holds native-script and translated names (`hi`, `ta`, `te`, …). `aliases` holds
    alternate spellings and historical names.
  - `tags` is for filtering and ranking (`community:agrawal`, `historical`, `region:MH`).
  - `attributes` is for list-specific data: a gotra's pravara and rishi, a rashi's Western gloss,
    ISO codes, LGD codes, years of validity, a kin term's path (ADR-0018).
  - `search_text` holds the romanised search keys of the label, labels and aliases
    (`app.core.textnorm.search_key`, ADR-0007). Searching for *भारद्वाज*, *Bhardwaj* and
    *Bharadwaja* finds the same term.
- These are **global reference data, not tree data**. They have no `tree_id` and no row-level
  security, and they hold no personal data.

### Seed files in the repository, loaded by an idempotent command
- The seed data lives in `backend/app/modules/vocabulary/data/*.json`, versioned with the code and
  reviewed in pull requests.
  - The jyotish lists are **generated from `astrology/vocab.py`** at load time, so validation and
    suggestion share one source.
  - Countries were generated once from ISO 3166-1 (pycountry) with Unicode CLDR English and Hindi
    names. Neither library is a runtime dependency.
- `python -m app.cli.load_vocabularies` upserts every vocabulary and term by code. A term removed
  from a file is set to `is_active = false`, never deleted, because stored records may still use
  its code. The deploy `migrate` step, `make migrate` and CI run it after `alembic upgrade head`.
- **Districts and sub-districts come from LGD (Local Government Directory)**, which is the
  authoritative source with codes and a change history. They are not typed in by hand.
  `load_vocabularies --lgd-districts <csv> [--lgd-subdistricts <csv>]` imports an LGD CSV download
  and links each district to its state by LGD state code. The seed ships the 36 current states and
  union territories, plus historical states, each with its ISO 3166-2 code and LGD state code.

### A read-only, authenticated API
- `GET /api/v1/vocabularies` returns the lists and their versions.
- `GET /api/v1/vocabularies/{code}/terms?q=&parent=&tag=&include_inactive=&cursor=&limit=`
  returns ranked results: exact or alias match, then prefix, then trigram similarity, then
  `sort_order`. It is filtered by `parent` (a parent term code, which gives the cascade) and by
  `tag`, with cursor pagination.
- Both endpoints need a signed-in user. That is consistent with an invite-only product and keeps
  the full dataset from being scraped anonymously; the data itself is not sensitive. Responses are
  `Cache-Control: private, max-age=3600`, and the frontend caches them per vocabulary version.

### Rules that do not change
- **A vocabulary is a typing aid. It never validates user input away and never infers anything.**
  Fields store `{code | null, value_as_recorded}`, and free text is always accepted (ADR-0003 no
  inference, CLAUDE.md master-data rule).
- Unknown / Not applicable / Prefer not to disclose are `ValueStatus` values on the field, not terms
  in a vocabulary.
- Closed sets that the schema already models as enums (relationship type, name type, sex at birth,
  event type and category, source type, document category, lineage) stay enums in code and
  OpenAPI. They are not duplicated as vocabularies.
- **Community / jati has no global vocabulary** (Q4 in `open-questions.md`). Its suggestions will
  come only from values already in the user's own tree, filtered by the viewer's permissions. That
  is separate work and is not part of these tables.

## Consequences
- One place to correct a spelling or add a gotra. The frontend `masterData` lists are replaced by
  API calls in a follow-up change; until then they remain as fallbacks.
- Districts, sub-districts and villages need an operator step (an LGD download) because LGD is not
  reachable from CI. Until then the `district` cascade returns an empty list and the UI falls back
  to free text, which it accepts anyway.
- The app role gets the same table grants as every other table (`GRANT_APP_ROLE_SQL`). Only the
  loader writes, and the API has no write endpoints. Revoking writes from the app role was
  considered, but `ensure_app_role` re-grants on every release, so the guarantee comes from the
  API surface instead.
- Villages (about 650,000) and world cities are **not** in these tables. They belong to the place
  gazetteer, which needs its own ADR (ranking against the tree's own places, historical names,
  geocoding provenance).

## Alternatives considered
- **Keep shipping lists in the frontend bundle.** Rejected: they drift from the backend, are too
  large for districts and sub-districts, and every correction needs a frontend release.
- **Seed through an Alembic data migration.** Rejected: every spelling fix would need a new
  migration, and the ORM-based normaliser can't safely be used from frozen migrations. Alembic owns
  the schema. The loader owns the data and is idempotent.
- **One table per list (`gotra`, `rashi`, …).** Rejected: 25 near-identical tables, endpoints and
  migrations. The differences between lists fit in `attributes`.
- **Call a live LGD or geocoding API on each keystroke.** Rejected: latency, availability, rate
  limits, and leaking what users type to a third party.
