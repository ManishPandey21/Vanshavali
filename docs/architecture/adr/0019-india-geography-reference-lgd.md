# ADR-0019: Indian geography reference data (LGD) and place cascades

- Status: Accepted · Date: 2026-11-07 (accepted as proposed, including the three open points) · Release: R2
- Relates to: ADR-0018 (global reference data, operator-loaded packs), ADR-0015 (place fields,
  precision, coordinate privacy, no PostGIS), ADR-0007 (search normalisation), ADR-0006 (field
  redaction), ADR-0014 (pilot hosting, backups)
- Plan: [india-master-data-and-smart-forms-plan.md](../india-master-data-and-smart-forms-plan.md),
  Phase B; open question Q15

## Context
Families type the same village a dozen ways ("Rampur", "Rampura", "रामपुर"), with the wrong district,
or with a district that was split in 2008. `place` already stores `district`, `state`, `country`
and a free-text `lgd_code` (ADR-0015), but nothing helps the user pick a real place.

India's **Local Government Directory (LGD)** gives every state, district, sub-district, village and
urban local body a stable code. It records renames, splits and merges, and it is published as open
data under the Government Open Data Licence – India (GODL-India), which requires attribution. India
Post's **PIN directory** (data.gov.in, also GODL-India) maps PIN codes to post offices and their
districts.

The data is large (about 6.5 lakh villages and urban bodies) and changes every quarter. It must
never silently rewrite what a family recorded: a great-grandfather was born in "Rampur, Allahabad
district" even if that village is in Prayagraj district today.

## Decision

### 1. Scope of R2
- **In:**
  - Stage 1: states and union territories, districts, sub-districts (about 8,000 units).
  - Stage 2: villages and urban local bodies, loaded state by state.
  - Stage 3: the India Post PIN directory.
  - The ancestral-village suggestion (§8).
- **Out:**
  - gram panchayats (a later stage);
  - historical or pre-1947 boundaries (Q15: those places stay free text with a historical name);
  - places outside India;
  - **coordinates**. The PIN directory's office coordinates are not imported: an office point is
    not a village location, and ADR-0015 keeps coordinates optional and user-entered.

### 2. Global, read-only reference data
- New tables hold reference data only, never tree data:
  - `geo_snapshot`;
  - `geo_unit` and `geo_unit_alias`;
  - `pincode_office`.

  They need no RLS. The application role gets `SELECT` only, and the operator CLI loads them as
  the schema owner, like ADR-0018's packs.
- **Units are versioned, not copied per snapshot.** Each `geo_unit` row records an LGD code at one
  version:
  - `lgd_code`, `level` (state, district, sub_district, village, urban_body) and
    `parent_lgd_code`;
  - `name_en`, `name_local` and `local_script`;
  - `first_snapshot` and `last_snapshot`;
  - `successor_codes`, when LGD records a merge or split.

  An unchanged unit keeps one row across snapshots. A renamed, moved or retired unit gets a new
  row, or a closed one. Queries read the rows valid in the **active** snapshot. Partial indexes on
  current rows keep this fast.
- **Aliases** (`geo_unit_alias`): alternative and historical names that LGD publishes, plus
  curated additions, which change only by code review. A family's own spelling stays on *their*
  place (`local_names`). It is never pushed into the global table.

### 3. Snapshots: stage, review, activate, roll back
- **Files.** The operator downloads the LGD and India Post files and runs
  `python -m app.cli.geo import --stage {1|2|3} [--state CODE] --snapshot YYYY-MM --file … --sha256 …`.
  - The app never fetches data over the network.
  - The checksum must match.
  - The snapshot records source URL, download date, licence, checksum and row counts.
- **Change report.** An import is staged, never live. It produces a report against the active
  snapshot: new, renamed, moved to another parent, merged or split (with successors), and retired
  codes, plus PIN offices whose district could not be matched. The report comes as CSV plus a
  summary.
- **Activation.**
  - `python -m app.cli.geo activate SNAPSHOT` makes a reviewed snapshot active, and is recorded in
    the audit log.
  - The previous snapshot stays available: `activate PREVIOUS` is the rollback.
  - The CLI refuses to activate a snapshot whose counts fall outside the expected ranges (for
    example, more than 5% of villages retired at once) unless `--accept-large-change` is given.
- **Validation.** Names go in as plain text: control characters are rejected, they are NFC
  normalised, and they are length-limited. The UI renders them as text. The importer also refuses
  rows with unknown parents and refuses cycles.
- **Cadence.** Quarterly LGD snapshots (Q15). PIN data is refreshed when India Post publishes.

### 4. Tree places keep their own record
- Picking a unit in the cascade fills the tree's `place`:
  - `lgd_code`, `place_type`, `canonical_name`, `district`, `state` and `country = India`;
  - a new `lgd_snapshot_id`, the snapshot the code was picked from.

  Everything except the code stays editable: the family's spelling wins.
- **Reference updates never rewrite tree data.** When the active snapshot renames, moves or retires
  a linked code, the place shows a non-blocking note, for example "LGD now lists this village under
  Prayagraj district (since 2026-02)". The user may update the place. Nothing changes otherwise.
- **"My village is not listed"** keeps a free-text place. The district and state chosen in the
  cascade fill `district` and `state` as text, and `lgd_code` stays empty. A code only links an
  exact unit.
- Historical, pre-1947 and outside-India places work exactly as today.

### 5. Names and search
- Search covers English names, local-script names and aliases. They are normalised with the
  existing `search_key` and `romanize` (ADR-0007), so "रामपुर", "Rampur" and "Raampur" meet.
- Results are scoped by parent (state, district, sub-district) where given, ranked exact → prefix
  → trigram, and report the match reason ("alias", "local name").
- The sub-district level takes the label each state uses: Tehsil, Taluka, Mandal, Block, Circle or
  Sub-division. This comes from a small, reviewed mapping in code, shown in English and Hindi.

### 6. API
Under `/api/v1`:
- `GET /geo/units?level=&parent=&q=&cursor=` returns children of a parent, or search results, with
  cursor pagination.
- `GET /geo/units/{lgd_code}` returns the unit, its ancestors and its successors, if any.
- `GET /geo/pincodes/{pin}` returns the post offices with their district and sub-district
  candidates. It *suggests* them and never picks a village.

All three:
- **Access:** signed-in users only.
- **Limits:** rate-limited per user.
- **Data:** no tree data.
- **Caching:** responses carry the active snapshot id, so they cache well (`ETag`).
- **Rollback:** `VSH_GEO_ENABLED=false` makes them answer 404, and the UI falls back to the
  free-text place fields. This is the same rollback as ADR-0018.

### 7. Interface
`PlaceCascade` is used on the Places page, in vital and event places, for the ancestral village
(heritage) and for land parcels (property).
- **Picking:** State → District → Sub-district → Village/Town, each a type-ahead. There is also one
  "search all villages" field, a PIN box that suggests the upper levels, and "My village is not
  listed".
- **Script:** local-script names are shown next to the English ones, with `lang` markup.
- **Device:** it works on a phone.
- **Accessibility:** keyboard and screen-reader friendly, the same combobox pattern as
  `SmartSelect`.

### 8. "Remember the ancestral village"
When someone is added to a branch whose heritage profile has an `ancestral_village` assertion, the
place fields *offer* that village as a visible, dismissible suggestion. Accepting it records the
user's own choice for that person. Nothing is inferred or filled silently: CLAUDE.md's rule on
master data applies.

### 9. Privacy, licence and attribution
- **Privacy:** linking to LGD adds no personal data. A village name stays in the existing
  `BIRTH_PLACE_DETAIL` field group, redacted for protected people exactly as today (ADR-0006).
  Coordinates are not derived from LGD (§1).
- **Logging:** search queries go in the query string, and only request paths are logged.
- **Licence:** GODL-India attribution ("Source: Local Government Directory, Government of India;
  India Post", with the snapshot date) is shown under the cascade and on the About page, and is
  written into the family archive's README.

### 10. Acceptance
Measured on the full village table on pilot-sized hardware (ADR-0014):
- **Speed:** cascade children p95 < 50 ms; name search p95 < 150 ms; importing the largest state
  < 5 min.
- **Footprint:** documented.
- **Backups:** included in the backup drill. Reference data can also be re-imported from the
  recorded files.

## Consequences
- One migration with a downgrade: the four tables, plus `place.lgd_snapshot_id`.
- **Storage:** an estimated 300–500 MB including trigram indexes, to be confirmed by the benchmark.
- **CI:** CI imports a small committed fixture (two districts, with a rename, a split and a PIN
  mismatch), not the national files.
- **Threat model:** a new row covers malicious or corrupt import files, oversized changes, search
  abuse, and reference updates rewriting tree data.

## Alternatives considered
- **A commercial or online geocoder (Google, Mappls…).** Rejected: it sends families' place
  searches to a third party, costs money per call, and has licence limits on storing results.
- **Copy a snapshot's whole table each quarter.** Rejected: about 6.5 lakh rows per snapshot grows
  without bound. Versioned rows store only the changes.
- **Copy LGD units into each tree as places.** Rejected: duplicates national data per family and
  makes updates a data migration of family records.
- **Overwrite linked tree places when LGD changes.** Rejected (§4): genealogical places are
  historical facts as the family recorded them.
- **PostGIS boundaries.** Rejected: nothing here needs geometry, and ADR-0015 keeps PostGIS out.
- **OpenSearch for place search.** Deferred: trigram search in PostgreSQL should meet the benchmark
  (ADR-0007 keeps OpenSearch for later).
- **Import post-office coordinates.** Rejected for R2 (§1).

## Stress test
1. *Can a quarterly update change what a family recorded?* No. Codes are linked, never
   overwritten, and a change only adds a note the user may act on (§4).
2. *What if a bad file is imported?* It is staged and checksummed, it produces a change report,
   and activation needs the operator. Large changes need an explicit flag, and the previous snapshot
   is one command away (§3).
3. *Can the reference tables leak family data?* They hold none. Families' spellings stay in their
   trees, and aliases change only by code review (§2).
4. *What if LGD lacks the village?* "My village is not listed" keeps free text, with the district
   and state as text (§4).
5. *What about a place that no longer exists, or existed before 1947?* Free text with historical
   names, as today (§1, Q15).
6. *Does the PIN code pick the village?* No. It only suggests the upper levels (§6).
7. *Is it fast enough on the pilot VM?* That is the acceptance benchmark (§10). If it fails, the
   fallback is to narrow searches to a chosen state before going to OpenSearch.
8. *Does it work when switched off?* Yes. The free-text place fields work as today (§6).

## Open points for the reviewer
- **Who activates a snapshot.** Proposal: the operator CLI with an audit entry for R2, and a
  system-admin review page later.
- **Urban detail.** Proposal: urban local bodies only for R2, with wards later if families ask.
- **Fixture data.** Proposal: a small real LGD extract under GODL-India with attribution, rather
  than synthetic names, so the importer is tested on the real file layout.
  *Implementation note (7 Nov 2026):* LGD's download directory is a session form with a captcha, and
  data.gov.in is not reachable from the build environment. So the first fixture is synthetic, in the
  published column layouts, and labelled as synthetic. The importer matches headers tolerantly and
  refuses files it does not recognise. Replacing the fixture with a real one-district extract,
  downloaded by hand, is tracked as a follow-up.

## Implementation notes (7 Nov 2026)
Built as decided. These points refine the ADR where the data or the code needed it:

1. **LGD codes are unique per level only** (district 9 and state 9 can both exist). So a unit is
   identified by its level and code:
   - `place` gets `lgd_level` next to `lgd_snapshot_id`;
   - `GET /geo/units/{lgd_code}` needs `?level=`.
2. **Ancestor scopes.** `GET /geo/units` takes `parent_level` with `parent`, so a search can be scoped
   to a state or district, not only to the direct parent. Each unit stores its state, district and
   sub-district codes for this.
3. **Snapshot rules that keep every step reversible:**
   - only the newest snapshot can be imported into;
   - a scope (a level, nationally or for one state) is imported once per snapshot;
   - a new snapshot needs the previous one active;
   - `discard` deletes the newest snapshot that is not active, unless places were linked under it.
     It reopens what that snapshot closed.
4. **Merges and splits.** LGD's plain downloads do not list successors. The operator passes them as
   a small `--successors` file prepared from LGD's change reports. Successors must name codes that
   the same import retires.
5. **PIN sub-districts.** These are suggested only when the India Post file has a taluk column; the
   current national file has none. The PIN suggestion stays district and state, never a village.
6. **Search.**
   - Searching across India needs three letters; two are enough within a chosen state or district.
   - The "search all" box covers villages and towns. A former district name ("Allahabad") is found
     in the District picker, through the historical alias recorded when the rename was imported.
   - Devanagari queries are also compared through the transliteration engine (ADR-0025), so
     "रामपुर" meets "Rampur".
7. **Notes (§4).** They cover a unit that was renamed, moved or retired. They also cover a unit whose
   district (or sub-district, or state) was renamed, which is this ADR's own Prayagraj example.
   - Saving the same pick again keeps the original snapshot, so the note stays.
   - `lgd_accept_current` re-links on purpose ("Update to LGD's current listing").
8. **Ancestral village (§8).**
   - The person form gains an optional *Family branch* field. The API already accepted `branch_ids`.
   - Choosing a branch whose heritage profile has an `ancestral_village` linked to a tree place
     offers that place for the birth place, as a dismissible suggestion.
   - `PlacePicker` carries the offer, so it can be reused elsewhere.
9. **Where the cascade appears.** `PlaceCascade` is built into `PlacePicker`. That covers vital and
   event places, the heritage ancestral village and property places, which is where land parcels
   take theirs. The Places page has it in the place editor.
10. **Read-only role.** The grant SQL revokes writes on the four tables whenever they exist, and it
    contains no `%` because `ensure_app_role` sends it through the driver.
11. **Benchmark (§10).** A synthetic national-scale run in the build container meets every target:
    - cascade children p95 5.9 ms;
    - search p95 79 ms all-India and 88 ms within a state;
    - largest-state import 14 s;
    - 382 MB with indexes.

    Measuring led to ancestor-column indexes, exact-first search with prefix indexes and a 0.4
    trigram threshold (`docs/operations/performance.md`). The run on pilot hardware with the
    national files stays open in `IMPLEMENTATION_STATUS.md`.
