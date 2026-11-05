# ADR-0018: Master data — controlled values vs extensible vocabularies

- Status: Accepted · Date: 2026-11-04
- Relates to: ADR-0003 (assertions, no inference), ADR-0006 (authorisation), ADR-0020 (kinship
  terms are controlled)
- Plan: [india-master-data-and-smart-forms-plan.md](../india-master-data-and-smart-forms-plan.md),
  release R1, phase A (minimal)

## Context
Dropdown values are scattered. Most are backend `StrEnum`s translated in the locale files. Four
static TypeScript lists live in `frontend/src/data/masterData` (gotras, kulas, nakshatras,
rashis), and only gotra suggestions reach the user. Families need suggestions for culturally
specific, open-ended fields (gotra, kuladevata, occupation…), in their own scripts and spellings,
with the right to add their own value. A design review warned against one generic vocabulary for
*every* dropdown: system values such as roles, privacy levels, relationship types or review states
must never become user-editable.

## Decision

### 1. Two kinds of list
- **Controlled values.** Closed sets with behaviour attached. They are validated by application
  code, changed only through schema or API evolution, and labelled through the locale files. They
  are never extended by users.
- **Extensible vocabularies.** Open, culturally variable *suggestions*. They are versioned,
  searchable in any script and by alias, source-attributed, and a family can add its own entries.
  The stored value is always what the person chose or typed. A vocabulary never fills in, infers
  or validates a person's cultural identity.

### 2. Classification of every dropdown (R1)

| Field / list | Kind | Where it lives | Unknown / Not applicable | Add my own |
|---|---|---|---|---|
| Roles, permissions, privacy levels, field groups, public mode | Controlled | `enums.py` + locale files | — | Never |
| Living status, sex at birth, name type, date/time precision, calendars, time source | Controlled | `enums.py`, `core/dates.py` | Built in (`unknown` values) | Never |
| Relationship types, lineage, sibling kind, union types | Controlled | `enums.py` (ADR-0003) | — | Never |
| Kinship terms for Smart Add | Controlled | `smartadd/terms.py` (ADR-0020) | — | Never (family wording comes later, as a vocabulary of *labels*) |
| Evidence status, confidence, provenance, review/claim/consent states | Controlled | `enums.py` | Built in | Never |
| Event types, life-event categories, significance, place types, location precision | Controlled | `enums.py` (ADR-0015) | `other` / `custom` + free title | Never |
| Document categories, source types, property types/events/units, interest types | Controlled | `enums.py` (ADR-0004, ADR-0010) | `other` | Never |
| Heritage attribute *names* and value status | Controlled | `HeritageAttribute`, `ValueStatus` | `ValueStatus` (unknown, not applicable, withheld) | Never |
| Nakshatra, rashi, tithi, paksha | Controlled (closed astronomical sets) | `astrology/vocab.py` (validation + aliases) | Field left empty | Never |
| **Gotra** | Vocabulary `gotra` | `masterdata` service | Through the heritage value status | Yes |
| **Kula / vamsha** | Vocabulary `kula` | `masterdata` | Through the heritage value status | Yes |
| **Kuladevata**, **Kuladevi** | Vocabularies `kuladevata`, `kuladevi` (start empty; grow from families) | `masterdata` | Through the heritage value status | Yes |
| **Occupation** | Vocabulary `occupation` | `masterdata` | Field left empty | Yes |
| **Honorific** (name prefix) | Vocabulary `honorific` | `masterdata` | Field left empty | Yes |
| **Language** (name language, family language) | Vocabulary `language` (English + the 22 Eighth-Schedule languages) | `masterdata` | Field left empty | No (closed for now; dialects later) |
| Community, jati/subgroup, religion | **No suggestions** | free text, private (Q4) | Through the heritage value status | — |
| Pravara, devak, family traditions | Later (phase G) | — | — | — |

Community, jati and religion deliberately get **no** vocabulary. Offering a list would steer
people towards caste and religious categories (Q4, PRS §2.3). They stay optional, private free text.

"Unknown" and "Not applicable" are not vocabulary terms. Fields that need them already have a
status (heritage `ValueStatus`), or are simply left empty. A term called "Unknown" would let
"unknown" pass as a known value.

### 3. Model (one migration, with downgrade)
- `vocabulary` (global): `key`, description, `version`, `source`, `licence`, `allows_custom`.
- `vocabulary_term` (global): `vocabulary_key`, stable `code`, `labels` (JSONB, per language),
  `aliases`, `scope` (regions/traditions), `parent_code`, `source_url`,
  `status` (`draft` / `reviewed` / `retired`), `sort_order`; unique `(vocabulary_key, code)`.
- `tree_vocabulary_term` (tree-scoped, **RLS**): a family's own entries, `vocabulary_key`,
  `code` (`t:` + slug, unique per tree and vocabulary), `label`, `aliases`. Promoting one into the
  global vocabulary is a manual, reviewed admin action outside the app (later).

Global tables carry public reference data only. They hold nothing about any family.

### 4. Packs and loading
Seed data is JSON packs in `backend/app/modules/masterdata/packs/`. Each pack carries its key,
version, source and licence. `python -m app.cli.masterdata load` is idempotent:
- it inserts new terms and updates changed ones;
- a term that disappears from its pack is marked **retired**, never deleted, so stored references
  keep resolving.

The pilot `migrate` service, the e2e database reset and the test fixtures run it after
`alembic upgrade`. JSON is used so the packs need no new dependency.

### 5. API
- `GET /vocabularies`: list of vocabularies (signed-in users).
- `GET /vocabularies/{key}?q=&lang=&parent=`: global terms. Retired terms are excluded unless
  `include_retired=true`.
- `GET /trees/{t}/vocabularies/{key}?q=`: global plus the tree's own entries (tree members).
- `POST /trees/{t}/vocabularies/{key}/terms`: add a family entry. Needs `PERSON_WRITE` and a
  vocabulary with `allows_custom`. If the label already matches an existing global or tree term
  (any script, alias or spelling), that term is returned instead of creating a duplicate.

Search uses the same normalisation as person search (`core/textnorm.search_key`: case, accents
and Devanagari ↔ Latin), so "कश्यप", "Kashyap" and "kashyapa" find the same term.

### 6. Stored values
- A heritage assertion picked from a vocabulary stores the label as entered in `value_text` and
  `{"vocabulary": key, "code": code}` in `value_json`. The server checks that the code exists
  globally or in this tree (422 otherwise). A retired or renamed term never makes an existing
  record unreadable, because the label is stored.
- Occupation and honorific remain free text. The vocabulary only suggests.

### 7. Rollback
`VSH_MASTERDATA_ENABLED=false` makes the vocabulary endpoints answer 404. The UI then falls back to
plain text inputs, and to the old static gotra list for heritage. Tree-specific entries are kept.
The static `src/data/masterData` lists are deleted once every consumer has switched and a release
has passed (plan, phase A transition step 3).

## Consequences
- One migration: two global tables and one tree-scoped table with RLS.
- Search is in memory per vocabulary: the R1 vocabularies have fewer than 100 terms each.
  Geography (phase B, ~6.5 lakh villages) will need database-side search and its own ADR (0019).
- Nakshatra and rashi stay controlled and validated by `astrology/vocab.py`. Their duplicate
  frontend lists will be served from that module in a later increment.

## Alternatives considered
- **One vocabulary for every dropdown.** Rejected: makes system states user-editable and turns
  enum validation into data lookups.
- **YAML packs.** Rejected for now: needs a new dependency, and JSON is enough.
- **Seeding packs in a migration.** Rejected: packs change more often than the schema, and
  migrations that import a loader which later evolves stop being replayable.
