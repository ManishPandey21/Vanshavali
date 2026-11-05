# ADR-0019: Indian geography reference data (LGD and India Post)

- Status: **Proposed** · Date: 2026-11-05 (design for the next increment; no code yet)
- Relates to: ADR-0018 (master data), ADR-0025 (Super Admin console, change requests),
  ADR-0015 (places, geotags), open question Q15
- Plan: [india-master-data-and-smart-forms-plan.md](../india-master-data-and-smart-forms-plan.md),
  phase B / release R2

## Context
Families record ancestral villages, birth places and parcels. Today a `place` is free text with an
optional `lgd_code` column that nothing fills. The plan asks for State → District → Sub-district
(Tehsil / Taluka / Mandal) → Village / Town with PIN suggestions, historical names and "my village
is not listed". The volume (≈ 6.5 lakh villages, ≈ 1.5 lakh post offices) rules out the in-memory
vocabulary model of ADR-0018, and the data has an authoritative publisher.

## Decision (proposed)

### 1. Three kinds of geographic data, kept apart
| Kind | Where | Who changes it |
|---|---|---|
| **Official reference** (LGD units, India Post offices) | `geo_unit`, `geo_pin_office`, per snapshot | Only by activating a validated snapshot (§3) |
| **Curated additions** (aliases, local-script names, historical names, corrections, units outside LGD) | `geo_unit_alias`, `geo_unit` rows with `origin = curated` | Super Admin change requests (ADR-0025 §3), four-eyes required |
| **Family places** | tree-scoped `place` (RLS), optional `lgd_code` | Family members, as today |

An official row is never edited in place. A correction is a curated alias or a curated successor
mapping, so the next official snapshot does not silently undo it and the source stays visible.

### 2. Model
- `geo_snapshot`: source (`lgd` / `india_post`), source URL, download date, licence (GODL-India,
  attribution text), SHA-256 of each file, row counts per level, status (`staged` / `validated` /
  `active` / `superseded` / `failed`), validation report (JSONB), uploaded/activated by.
- `geo_unit`: `id`, `snapshot_id`, `level` (`country`, `state`, `district`, `subdistrict`,
  `block`, `gram_panchayat`, `village`, `town`, `ulb`), `code` (LGD code, or `x:` + slug for
  curated), `parent_id` (FK, same snapshot), `name_en`, `name_local`, `local_script`,
  `local_term` (Tehsil / Taluka / Mandal / Circle…), `valid_from/to`, `successor_codes[]`,
  `origin` (`official` / `curated`), `search_key` (generated, trigram index).
  Unique `(snapshot_id, level, code)`. A CHECK and trigger ensure `parent.level` is the allowed
  parent level (village → subdistrict, subdistrict → district, district → state…), so invalid
  parent-child combinations are rejected by the database.
- `geo_unit_alias`: unit code + level, alias, script, kind (`spelling` / `historical` /
  `local_script`), valid period, source. Survives snapshot changes (keyed by code, not row id).
- `geo_pin_office`: PIN (`^[1-9][0-9]{5}$`), office name, office type (H.O./S.O./B.O.), delivery
  status, district/state codes, optional village/town code; **many-to-many** with units through
  `geo_pin_unit`. A PIN never implies exactly one village.

### 3. Staged import and activation
1. `python -m app.cli.geo stage --source lgd --file … --snapshot 2026-10` (or the console upload,
   CSV/JSON only, size-capped, run as an RQ job with row and time limits) loads into a **staged**
   snapshot. Nothing users see changes.
2. Validation job: schema, code formats, hierarchy (missing parents, wrong levels), duplicates,
   and a **diff against the active snapshot**: added, renamed, moved, split/merged, retired codes.
3. The console shows the report (counts and samples, downloadable). One admin approves, **a second
   admin activates** (four-eyes, ADR-0025 §3). Activation flips `active` in one transaction; the
   previous snapshot becomes `superseded` and stays available for **rollback** (reactivate it).
4. Retired codes stay resolvable: lookups by code search the active snapshot, then older ones,
   and follow `successor_codes`.

### 4. API (public reference data; signed-in users; rate-limited)
- `GET /geo/units?level=&parent=&q=&cursor=`: children of a unit, or name search (any script,
  aliases and historical names), cursor pagination.
- `GET /geo/units/{level}/{code}`: one unit with its ancestors, aliases and successors.
- `GET /geo/pincodes/{pin}`: offices and the units they serve (suggestions only).
- Admin: `/admin/master-data/geo/snapshots…` (stage, validate, report, activate, roll back) and
  curated aliases/units through `vocabulary_change`-style change requests.

### 5. UI
`PlaceCascade`: Country → State/UT → District → Sub-district (label from the state's
`local_term`) → Village/Town → PIN/post office, plus "PIN first" (suggests offices and units) and
"My village is not listed / historical / outside India" (stays free text with a flag). It
pre-fills editable text on the family `place` and stores `lgd_code`; it never overwrites a family's
historical name.

### 6. Acceptance
Benchmarks from the plan (children p95 < 50 ms, search p95 < 150 ms on the full village table,
one large state imported in < 5 min); invalid parent/child rejected; many-to-many PIN; retired
codes resolve; rollback restores the previous snapshot; no tree data in any geo endpoint.

## Open questions (owner)
- **Licence and attribution** wording for LGD (GODL-India) and the India Post directory, and
  whether India Post data may be redistributed in the app. Until answered, no official data is
  committed to the repository; tests use small synthetic fixtures.
- Q15: refresh cadence (quarterly proposed) and whether pre-1947 units are needed.
- Gram panchayat and block levels: stage 4, optional.

## Alternatives considered
- **Geography as ADR-0018 vocabularies.** Rejected: in-memory search does not scale, and the
  hierarchy needs database constraints.
- **Edit official rows directly.** Rejected: the next snapshot would undo or conflict with edits,
  and provenance would be lost.
- **External geocoding API at entry time.** Rejected for now: privacy (family places leave the
  platform) and cost.
