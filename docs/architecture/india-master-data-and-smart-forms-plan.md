# Plan: India Master Data, Smart Forms and the next feature wave

Status: **proposed, revision 2** (audit and plan written 4 Nov 2026, before any code; revised the
same day after a design review of PR #27, see §8).
Input: an external product review that lists the features shown on the landing page, compares
Vanshavali with Indian and international genealogy platforms, and proposes an India-specific feature
catalogue, master dropdown data and a roadmap. Its recommended first step is "India Master Data Pack +
Smart Add Relative Wizard".

This document (1) checks each claim in that review against the code, (2) lists what is missing, and
(3) sets out a phased plan, delivered as five releases (R1–R5, §4) with acceptance criteria (§5). It follows the working rules in `CLAUDE.md`: decisions that touch
relationship modelling, privacy, calendars, households or OCR/AI provenance get an ADR **before**
code, and every phase lists its migrations, APIs, UI, tests and threat-model updates.

---

## 1. Audit: what the review saw versus what the application does

The review says it did not check whether the features shown on the landing page work inside the
application. This section does that from the code (`backend/app/modules/*`, `frontend/src/*`,
`IMPLEMENTATION_STATUS.md`, `docs/requirements-traceability.md`). The stack was not run for this
audit; "Verified" means automated tests for it exist and passed at the last recorded run (2 Oct 2026).

| Feature from the review | What the application actually has | Status | Gap |
|---|---|---|---|
| Family tree, sample 20-member Iyer family | `app.cli.seed_demo` seeds a fictional **"Iyer Family (demo)"** (four generations) through the real service layer. The landing page shows a separate animated **Sharma** tree and an in-browser "plant your tree" try-out | Verified | None. The demo is a seed for dev/pilot accounts, not a public sample; there is no read-only public demo tree |
| Indian relationships (Dada, Nani, Tau, Chacha, Mama, Bua, Mausi…) | `/relationship-path` returns an English label plus a kinship **chain**; `frontend/src/lib/kinship.ts` maps about 55 chains to **Hindi** terms. Shown on the relationship calculator page only | Partial | Hindi only, and only in the frontend. No elder/younger distinction (shows "चाचा / ताऊ", "देवर / जेठ"). Missing terms from the North-Indian diagram: Didi/Bhaiya, Tai, Jethani/Devrani split, Bhai Sahab vs Saala, Behnoi, Nandoi, Bhayo, Samdhi/Samdhan. The term is not shown on a person's profile from *your* point of view ("Ramesh is your Mama"). English UI shows "uncle" only. No regional vocabularies (Marathi, Tamil, Bengali…), and a family cannot choose its own words |
| Heritage: Gotra, Pravara, Kuladevata, Kuladevi, ancestral home | `assertion` model with 16 `HeritageAttribute`s (gotra, pravara, kula/vamsha, community, jati, religion, ancestral village/house, tharavad, kuladevata, kuladevi, temple, traditions, language traditions…), Unknown / Not applicable / Withheld, disputes, preferred value, branch-level profiles, **never inferred** (test) | Verified | Only Gotra has suggestions (a `<datalist>` from `src/data/masterData/gotras.ts`). No Devak, ancestral occupation or surname-history attributes. Pravara is free text, not linked to the chosen gotra. No Kuladevata/Kuladevi catalogue |
| Joint families, marriages, biological/adoptive/step | Typed relationship edges (biological, adoptive incl. dattak, step, foster, guardian, spouse, partner, divorced, separated), multiple and ordered unions, lineage toggles, households with karta and membership over time, branches with descent rules | Verified | None at model level. Entry is slow (see Smart Add below) |
| Tree views: fan, pedigree, cluster, relationship exploration | Fan chart, pedigree, family tree, relationship web (progressive, path highlight), lifespans, life story, tile-free map; SVG/PNG/print; Remotion MP4 exports | Verified | No "cluster" view by branch/household as such (the relationship web covers exploration). Large-tree rendering is still Partial (§26.2) |
| Matrimonial biodata with horoscope | Astrology profile (rashi, nakshatra, birth-time provenance, Kundli as evidence, birth-conflict report) exists. **Biodata generator was removed** from the prototype | **Not available** (DEFERRED P2) | The landing page does not claim biodata; the review's observation likely came from the old prototype or another site |
| Documents, records, evidence | Document vault (scan, encrypted write-once, previews, versions, signed URLs), sources and citations, evidence status, traditional registers (bahi/panda), OCR (eng+hin) → proposals → human review | Verified | No "verification status" workflow for family review (see Family-verified ancestry) |
| Ancestral property: land, houses, inheritance, partition | Property, parcels (ULPIN, khasra…), exact-fraction interests, events, partition, timeline, lineage, "not a legal title opinion" | Verified | Property dropdowns (type, relation) are enums, not shared master data; no LGD-linked village on parcels |
| Privacy, controlled sharing, GEDCOM export | Privacy levels + field overrides, minor protection, deny-by-default RBAC, branch scope, RLS, consent ledger, claim links, erasure, GEDCOM 7 export, archive ZIP | Verified | DPDP grievance/data-subject-request inbox DEFERRED; lawful basis for unclaimed living relatives open (Q13) |
| Cultural archive: ritual guides, knowledge, stories, historical timeline | Landing-page sections (traditions, keepers, stories, timeline) are **static marketing content**. In the app: life events with categories (naming, mundan, upanayana…), tree-wide timeline, life story view | **Landing only** | No in-app ritual guides, family knowledge entries, oral-history stories or recordings |

**Conclusion.** Eight of the ten features are real and tested. Two are not: matrimonial biodata
(deliberately deferred) and the cultural archive (landing page only). Kinship terms are the
weakest "verified" feature: correct but narrow.

### 1.1 Review's other suggestions, checked

| Suggestion | Exists today | Gap |
|---|---|---|
| Add relatives by relationship, not by drawing | Person profile → Add parent / spouse / child / sibling dialog (`AddRelativeDialog`, `POST /people/{p}/relatives`) | Only 4 direct relations. "Add my Mama" needs three steps (add mother, open her, add brother). No elder/younger choice |
| "How am I related?" | Relationship calculator (any two people, path, common ancestors) | Not personalised: does not default to *me* (claimed profile), not shown on profile cards |
| Duplicate detection and merge | Duplicate candidates + reversible merge with admin approval | None |
| Review and approval of changes; version history | Append-only audit log; merge/extraction proposals reviewed | **Change proposals, comments, challenges DEFERRED** (PRS §28) |
| Family calendar (birthdays, anniversaries, Punyatithi, Shraddha) | Events + reminders (email live; SMS/WhatsApp adapters mocked) | **Gregorian only**: tithi reminders explicitly unsupported (`notifications/schedule.py`). Calendars: Gregorian, Julian, Vikram Samvat, Shaka, Hijri (non-Gregorian dates are stored as recorded and placed approximately on the time axis). No Paksha/Tithi/Masa on dates. No Bengali, Tamil, Malayalam calendars (Q6) |
| Migration map | Migration events + map with routes | Live tiles DEFERRED (by design) |
| Geography dropdowns (State → District → Tehsil → Village → PIN) | `place` has `lgd_code`, hierarchy, locality/district/state/country **as free text** | No reference geography, no cascading picker, no PIN validation |
| Hindi + English, transliteration | UI en/hi (key-parity test). Names in any script; search is transliteration-aware (`indic-transliteration`) | No transliteration *suggestion while typing*; data-language list not standardised (`name_record.language` is free text); no other UI languages (Q8) |
| WhatsApp invitations, elder voice notes | WhatsApp share of claim links (ADR-0011). Audio/video document categories | No in-browser recording, no "Ask an elder" flow, no speech-to-text |
| Family book / PDF export | Charts print to PDF | Narrative family book DEFERRED |
| Cross-family connections | — | Not planned yet (privacy-heavy) |
| Activity feed, reunions, announcements | — | Not planned yet |
| Low-bandwidth, elder-friendly mobile | Responsive, mobile-first, WCAG 2.2 AA automated audit | No PWA/offline drafts, no "lite" mode, no large-text mode |
| Knowledge assistant | — | Not planned yet |

### 1.2 Master data today

`frontend/src/data/masterData/` holds four static TypeScript lists (gotras with an unverified
`pravara` string, kulas, nakshatras, rashis). Only gotras (heritage datalist) and nakshatras/rashis
(astrology tab) are used. Everything else is a backend `StrEnum` (relationship types, date precision,
evidence status, document and property categories, place types…) translated in `en.json`/`hi.json`.
There is no versioning, no source attribution, no aliases outside gotras, no tree-level custom
entries and no regional labels beyond Hindi. **This is the foundation the review asks for, and it
does not exist yet.**

---

## 2. Principles carried into every phase

1. **Store facts, compute words.** Only parent/child/spouse/sibling edges (plus type, lineage,
   order) are stored. Kinship terms ("Mama", "Periyappa") are computed for a viewer, language and
   family vocabulary. A stored "Mama" relationship is never created (already the ADR-0003 model).
2. **Suggest, never infer.** Master data are suggestions. Gotra, Pravara, religion, jati and
   kuladevata are never derived from a surname, place or relative (existing test stays the gate).
   A kinship term chosen in Smart Add establishes a **relationship path only**: it does not set
   gender identity or any other sensitive attribute (see Phase D).
3. **Two kinds of list.** *Controlled system values* (roles, privacy levels, relationship types,
   evidence and review states, date precision…) stay code-validated enums that change only through
   schema/API evolution. *Reference and cultural suggestions* (gotra, devak, kuladevata,
   occupation, languages, geography, kinship terms…) live in the master-data service. Unknown,
   Not applicable and "Add my own" are offered **where they are semantically valid**, not on every
   dropdown.
4. **Nothing permanent without the user seeing it.** Composite writes (Smart Add, proposals,
   imports) show a preview and need explicit confirmation; provisional people are always visibly
   distinct from confirmed ancestors.
5. **Privacy-first defaults stay.** New features inherit person privacy, minor protection and RLS,
   and reuse the existing privacy serializer. Consent, authorisation, retention and deletion rules
   for any new collection, voice or export workflow are written into the threat and privacy models
   **before** that phase starts (§6).
6. **Proposals before facts.** Speech-to-text, OCR, assistant answers and other families' data enter
   as proposals that a person reviews (CLAUDE.md rule 7, ADR-0009).
7. **Evidence, provenance and approval are separate.** *Evidence status* says how well a fact is
   supported, *provenance* says where it came from, *review state* says whether the family has
   approved it. None is folded into another.

---

## 3. The phases

The phases A–O are the long-term roadmap. They are **delivered as releases R1–R5** (§4), each
behind a feature flag, each ending with lint, typecheck, tests, build, a live-stack Playwright run,
the a11y audit and the acceptance criteria in §5.

### Phase A: India Master Data service — ADR-0018

**Goal.** One versioned service for *reference and cultural* vocabularies. System enums are out of
scope (principle 3).

- **Classification first.** ADR-0018 contains a table of every dropdown in the app, marked
  *controlled enum* or *extensible vocabulary*, and for each vocabulary whether Unknown / Not
  applicable / Add my own apply. Initial vocabularies: gotra, pravara, devak, kuladevata, kuladevi,
  kula/vamsha suggestions, occupation, honorific, name format, language (English + 22 Eighth-Schedule
  languages, ISO 639 codes and scripts), religion/tradition (optional suggestions), family event
  type suggestions, record source, property type labels, nakshatra, rashi, paksha, tithi, masa,
  kinship terms. Relationship types, roles, privacy levels, evidence status and review states stay
  enums with translated labels.
- **Model (migration, with downgrade).**
  - `vocabulary` (global): `key`, description, owner, version.
  - `vocabulary_term` (global): stable `code`, `labels` JSONB per language, `aliases`, `scope`
    (regions/traditions), `parent_code` (e.g. pravara → gotra), `source` + `source_url`,
    `status` (`draft` / `reviewed` / `retired`), `valid_from/to`; changes audited.
  - `tree_vocabulary_term` (tree-scoped, RLS): a family's own entries and preferred spellings.
    Promotion to global is a manual, reviewed admin action.
- **Stored values.** Records store the term `code` plus the label as entered; a retired or renamed
  term never makes an existing record unreadable.
- **API.** `GET /api/v1/vocabularies/{key}?q=&lang=&scope=&parent=` (cursor pagination, ETag),
  `GET /t/{tree}/vocabularies/{key}` (global ∪ tree terms), `POST /t/{tree}/vocabularies/{key}/terms`
  (contributors), admin curation endpoints.
- **Seed packs** (`backend/app/modules/masterdata/packs/*.yaml`, CLI importer, each with source and
  licence). Gotra seed with aliases; **pravara links `draft` until sourced**; devak and
  kuladevata/kuladevi start empty and grow from reviewed family submissions.
- **Transition plan.**
  1. Ship the service and packs behind flag `masterdata`; forms keep reading
     `src/data/masterData/*` and enum labels.
  2. Switch each form to `SmartSelect` one at a time; existing free-text values stay as entered and
     are shown as-is (no rewrite of stored data).
  3. When every consumer is switched and a release has passed, delete `src/data/masterData/*` and
     update CLAUDE.md. Rollback = turn the flag off; tree-custom terms are kept.
- **Frontend.** `useVocabulary(key)` and one accessible `SmartSelect` combobox (search label or
  alias in any script; groups "Suggested / Your family / Other"; Unknown / Not applicable / Add my
  own only where the vocabulary allows them).
- **Tests.** Pack schema validation; en/hi label parity; versioning (retired term still renders);
  tree terms isolated across trees (authz + RLS); no inference across every cultural vocabulary;
  SmartSelect keyboard, screen-reader names and Devanagari search; migration round trip.

### Phase B: Indian geography reference — ADR-0019

**Goal.** State → District → Sub-district/Tehsil/Taluka → Village/Town with stable LGD codes, PIN
lookup, historical names and "My village is not listed". Runs **in parallel** with R1 and never
blocks it.

- **Staged import** (`app.cli.geo import --stage … --snapshot YYYY-MM`, idempotent):
  1. States/UTs, districts, sub-districts (≈ 8,000 rows).
  2. Villages and urban local bodies, **state by state** (≈ 6.5 lakh in total).
  3. India Post PIN/post-office directory (PIN ↔ office ↔ district, many-to-many).
  4. Optional: gram panchayats.
- **Provenance checks before activation.** Each snapshot records source URL, download date,
  licence (GODL-India, attribution), checksum and row counts; an import produces a change report
  (new, renamed, split, retired codes) that an admin reviews before the snapshot becomes active.
  The previous snapshot stays available for rollback.
- **Model.** Global read-only `geo_unit` (`lgd_code`, `level`, `parent_lgd_code`, English and
  local-script names, `valid_from/to`, `successor_codes`), `geo_unit_alias`, `pincode_office`,
  `geo_snapshot`. A tree `place` keeps its own record and *optionally* references a unit via the
  existing `lgd_code`; district/state text is pre-filled but editable. Historical, pre-1947,
  unlisted and outside-India places stay free text.
- **API.** `GET /api/v1/geo/units?level=&parent=&q=`, `GET /api/v1/geo/pincodes/{pin}`; public
  reference data, rate-limited, no tree data.
- **UI.** `PlaceCascade` (Places, vital and event places, ancestral village, parcels); the tehsil
  label follows the state (Tehsil / Taluka / Mandal / Block); PIN lookup *suggests* offices.
- **"Remember my ancestral village".** A branch's `ancestral_village` assertion is offered as a
  visible, dismissible suggestion; saving records the user's own assertion.
- **Benchmarks (acceptance).** On the full village table on pilot-sized hardware: cascade children
  p95 < 50 ms, name search p95 < 150 ms, import of one large state < 5 min, total footprint
  documented; included in the backup drill.

### Phase C: Kinship engine v2 — "Relationship in my language" — ADR-0020

**Goal.** Correct regional terms from the viewer's point of view, with honest uncertainty.

- **Age order between the right pair.** Terms compare the relevant siblings, not the viewer:
  Tau vs Chacha compares the uncle with the **father**; Jeth vs Devar compares the brother-in-law
  with the **husband**; Didi/Bhaiya compare the sibling with the speaker. The engine names the pair
  it compared in its explanation.
- **Sources of age order, in precedence:**
  1. A **family-confirmed** `relative_age` on the sibling pair (`elder` / `younger`), recorded with
     who confirmed it; it wins over dates.
  2. Birth dates, only when both are precise enough to order them unambiguously (overlapping
     ranges, circa dates and conflicting birth claims give no answer).
  3. Otherwise **unresolved**: both terms are shown ("चाचा / ताऊ") with a prompt "Is he older or
     younger than your father?" whose answer records (1).
- **Unknown sex on a hop** gives the neutral reading with alternatives (e.g. "mother's sibling —
  Mama / Mausi"), never a guess.
- **Backend term resolution.** A `kinship` module reads term data from the master-data service,
  keyed on chain, sex of each hop, age order of the relevant pair, speaker's sex where languages
  differ, language and region. `/relationship-path` returns `terms: [{lang, term,
  transliteration, alternatives, basis}]` next to the existing label and chain; `kinship.ts`
  becomes a renderer.
- **Coverage.** R1: every term in the North-Indian diagram supplied with the review (Dada/Dadi …
  Samdhi/Samdhan, Nati/Natin) plus half, step and adoptive variants. R4: regional packs (Q14),
  each `draft` until native-reviewed.
- **Family vocabulary** overrides (e.g. "Bhayo" vs "Bhabhi") per tree or branch.
- **"Me" perspective** only when the user has a claimed profile; otherwise nothing is assumed.

### Phase D: Smart Add Relative wizard and progressive profiles

**Goal.** "Whom do you want to add?" in one guided flow that never inserts people the user has not
seen and confirmed.

- **Choose.** Father, Mother, Spouse, Son, Daughter, Brother, Sister (each with an optional
  "older / younger than <anchor>" answer that records `relative_age`), and "More relations" listing
  Phase C terms in the user's language. Each term maps to a path of basic edges.
- **Resolve each intermediate hop.** For "Mama": the anchor's mother is (a) the recorded mother,
  (b) another existing person the user picks (with duplicate suggestions), or (c) a new
  **provisional** person, explicitly chosen. With several candidates (two mothers, several unions)
  the user picks; the system never guesses.
- **Preview.** Before anything is written the wizard shows the full path and every record that will
  be created or linked ("Ramesh → Mother (existing: Sunita) → her brother (new)"). Nothing is
  persisted until the user confirms.
- **Commit.** `POST /t/{tree}/people/{p}/relatives/by-path` with the confirmed plan: one
  transaction, re-validated server-side (people still visible and in the same tree, no cycles, no
  duplicate parent of the same type, union exists), returns the created IDs and an undo token.
  "Undo" within the session soft-deletes exactly those records and edges.
- **Provisional people.** A `provisional` flag (ADR-0020, migration with downgrade): shown with a
  distinct badge and "unnamed" label, excluded from counts and exports by default, private
  (living-by-default; visible only to the creator and tree admins) and listed under "To complete".
  The flag records the person's origin and is kept: a name completes the details but verifies
  nothing; verification comes from the relationships' evidence (ADR-0020 §4, §7, amended 5 Nov).
- **Identity fields.** The chosen term sets neither gender identity nor sex at birth: `sex_at_birth`
  starts as "not recorded" and is stored only if the user enters it, in which case Phase C shows the
  definite word; otherwise it shows the neutral reading (amended 5 Nov; earlier drafts pre-selected
  it from the term).
- **Progressive form.** Step 1: name (with transliteration suggestion, original kept), living
  status, approximate year. "Add more details" expands date accuracy, place cascade (when R2 is on),
  occupation, honorific, name format and name language/script.

### Phase E: Unknown/custom review and the Hindi pass

Apply the ADR-0018 classification to every form (Unknown / Not applicable / Add my own only where
valid), native Hindi review of new strings, and the elder-friendly UX review in §5.

### Phase F: Family-verified ancestry (change proposals and review) — ADR-0021

- `change_proposal` (tree-scoped): proposer, target, **base revision** of each target record,
  diff, rationale, sources, status (`draft → awaiting_review → accepted / rejected / contested /
  stale`), reviewer, comments. Tree setting: contributors' changes to ancestors, relationships and
  heritage fields need review. A `REVIEWER` capability (RBAC change → threat model).
- **Bound to an exact revision.** Approval applies only if every target is still at its base
  revision; otherwise the proposal becomes `stale` and must be rebased and re-reviewed. The reviewer
  sees the diff against the current state, never a cached one.
- **Separate concepts (principle 7).** `EvidenceStatus` is unchanged (no `FAMILY_CONFIRMED`).
  Family approval is a separate `review_state` on the fact (`unreviewed / family_reviewed /
  contested`) with reviewer and time; provenance stays in `ProvenanceMixin`. The review's certainty
  words are UI labels over these: document-supported = SOURCED/CORROBORATED, family-reported =
  FAMILY_RECOLLECTION, estimated = imprecise date, disputed = DISPUTED, family-confirmed =
  `review_state = family_reviewed`.
- Challenge a fact → contested proposal. Per-person version history from the audit log, with revert.
- In-app notification centre.

### Phase G: Gotra/Pravara/Kuladevata and family traditions

- Heritage attributes `devak`, `ancestral_occupation`, `surname_history` (or historical
  `name_record`s with a period), multi-valued `family_language`.
- Pravara suggestions filtered by gotra **only from reviewed, sourced links**, always editable,
  with "associations vary by tradition".
- Kuladevata/Kuladevi catalogue from reviewed family submissions, linked to a temple `place`.
- In-app cultural archive: `tradition_entry` (ritual guides, customs, songs, recipes) with people,
  events, places, branch scope, privacy and sources.

### Phase H: Indian family calendar — ADR-0022

- **Gates before code:** Q16 (engine chosen and licence reviewed) and the regional conventions in
  Q6 approved. This phase **does not resolve Q6 by itself**; it implements whatever Q6 decides.
- Optional lunar component on `GenealogicalDate` (`masa`, `paksha`, `tithi`, `month_convention`,
  `region`), original text always kept.
- Tithi → next Gregorian date for a stated location, time zone and convention; reminders: solar
  date, lunar tithi, one-time, custom; Punyatithi and Shraddha event types. The reminder states the
  convention and place it used.
- Family calendar page; per-user ICS feed (private, revocable token; follows the viewer's privacy).
- **Accuracy tests:** golden tables per convention, several cities and overseas time zones, over
  several years incl. adhik masa and kshaya tithi, checked against published panchangs; tolerance
  and known-divergence cases documented.

### Phase I: Oral history — "Ask an Elder" — ADR-0023

- **Gates before code:** Q17 decided; privacy model updated with the rules below.
- `story`: title, narrator, interviewer, date/place, language, people tagged, privacy, consent
  record; media are vault documents.
- In-browser recording (MediaRecorder, Opus, resumable upload).
- **Ask an Elder link** on the ADR-0011 link infrastructure: single-purpose, expiring, one question,
  the elder's language; the elder (or guardian) gives recorded consent before recording; no account
  and no tree access.
- **Consent withdrawal:** the narrator can withdraw at any time; media, transcript and unreviewed
  proposals are erased; already-accepted facts keep their citation but lose the media link.
- **Retention:** raw audio is kept for a defined period (default proposed: until transcript review
  plus 90 days) unless the family explicitly chooses to archive it; transcripts follow story
  privacy; both covered by erasure and "remove me".
- **Other living relatives mentioned:** stories default to the most restrictive of narrator and
  tagged-person privacy; facts about other people become proposals governed by *their* privacy;
  a tagged relative can ask to be untagged or for the passage to be hidden.
- Speech-to-text self-hosted by default; external provider only per-tree informed opt-in (Q7/Q17);
  transcript → `extraction_proposal`s.

### Phase J: Duplicate detection inside Smart Add

Duplicate check in the wizard's resolve step, match reasons including LGD village and parents, and a
"possible duplicate" badge.

### Phase K: Family book, PDF and image export

- Server-side background job, self-hosted Indic fonts, signed download.
- **Access control, not watermarks.** Content goes through the existing privacy serializer as the
  exporter. Living people's private fields are excluded unless the exporter is entitled to them
  **and** the export scope permits them; including other living people's private details needs
  their recorded consent (or the tree policy that ADR defines). A watermark is added for
  traceability only. Exports are audited.

### Phase L: Elder-friendly, low-bandwidth mobile

- PWA, image compression, "large text / simple mode", data-saver.
- **Shared-device safety:** offline storage holds only the user's own drafts (no cached profiles of
  others); drafts are cleared on logout and after session expiry; a "this is a shared device"
  option shortens session lifetime and disables offline drafts; no sensitive data in service-worker
  caches (tests inspect the caches).
- Budget: < 200 KB gzipped JS on the tree home route; throttled-3G Playwright run.

### Phase M: Matrimonial biodata — ADR-0024 (later)

Consent-first: only the subject (or guardian of a minor) generates their own biodata; field-by-field
selection through the privacy serializer; other relatives' living data only with their consent;
expiring private link. **Non-goals:** compatibility scoring, guna milan verdicts, caste/gotra
matching.

### Phase N: Migration map, research links, cross-family connections, activity feed (later)

LGD-coded map points and optional self-hosted tiles; outbound links to FamilySearch India and
Abhilekh Patal (no scraping); cross-family connections by mutual admin consent (own ADR); activity
feed and announcements respecting privacy and branch scope.

### Phase O: Family Knowledge Assistant (later)

Deterministic kinship-query layer first (Phase C terms → engine → privacy filter → highlighted
path); optional LLM layer later (self-hosted by default, Q7) that answers only from visible records
with citations and offers "Ask a relative" instead of guessing.

---

## 4. Releases

| Release | Phases | Scope | Done when |
|---|---|---|---|
| **R1 — Core usability** | A (minimal: classification, service, kinship-term and occupation/honorific/language vocabularies), C (Hindi, North-Indian set, age-order rules), D, E (for the touched forms) | Smart Add Relative with preview, reliable Hindi relationship terms, progressive person entry | A user adds common relatives (incl. Mama, Nani, Bhabhi) through one guided flow, sees the correct Hindi term or an honest "चाचा / ताऊ" with a question, and no unconfirmed person is ever created |
| **R2 — India geography** | B (stages 1–3), "remember my ancestral village" | Searchable cascades, aliases, PIN suggestions | Users pick Indian locations without retyping; benchmarks in Phase B met |
| **R3 — Data integrity** | F, J | Change proposals bound to revisions, reviewer controls, challenges, review state, duplicates at entry | Family members can propose, review and challenge changes; stale approvals impossible |
| **R4 — Cultural depth** | G, rest of A, regional kinship packs (C) | Gotra/Pravara suggestions, Devak, Kuladevata, regional dictionaries, traditions archive | Heritage data structured and searchable; packs native-reviewed |
| **R5 — Engagement** | H, I, K, L | Family calendar and Punyatithi, oral history, family book, elder-friendly mobile | Each gated by its open question and privacy-model update |
| Later | M, N, O | Biodata, cross-family links, research and knowledge assistant | Own ADRs |

The full LGD import (R2) runs in parallel with R1 and does not block it.

**R1 progress (5 Nov 2026):** Smart Add Relative (ADR-0020), the minimal master-data service with
the ADR-0018 classification, and age-aware kinship terms in the calculator (ADR-0020 amendment) are
implemented (see `IMPLEMENTATION_STATUS.md`). Still open in R1: transliteration suggestions, leaving
provisional people out of headline person counts and a "To complete" list (privacy and export
exclusion are done, 5 Nov), and native Hindi review.

**Public-launch gate:** Q13 (lawful basis for living relatives who have not claimed their profile)
must be signed off by counsel before any public launch, regardless of which releases have shipped.

## 5. Acceptance criteria (in addition to the repository's existing requirements)

Before R1 starts:

1. ADR-0018 contains the master-data classification (controlled enum vs extensible vocabulary, and
   where Unknown / Not applicable / Add my own apply), with versioning and localisation tests
   planned.
2. ADR-0020 covers age-order precedence, provisional people and the Smart Add preview.
3. A migration and feature-flag strategy that rolls back without losing tree-custom terms or people
   created through Smart Add.

Before any release is declared complete:

4. **Smart Add:** never persists without confirmation; tests for an existing parent, duplicate
   parents, multiple unions, cycles, a hidden intermediate, cross-tree IDs (IDOR/BOLA), viewer
   denied, and undo.
5. **Kinship matrix (deterministic, Hindi):** paternal and maternal branches, elder / younger /
   unknown / conflicting age (comparing the correct pair), family-confirmed order overriding dates,
   unknown sex, half / step / adoptive, both speaker sexes, viewer perspective, and privacy
   filtering (no leakage through a hidden person).
6. **Master data:** versioning (retired terms still render), en/hi label parity, tree isolation.
7. Current backend and frontend CI green, a live-stack Playwright run, privacy-negative tests for
   the release, and a manual Hindi and elder-friendly UX review (large text, low-end Android,
   slow network) recorded in `docs/accessibility/`.

## 6. Security and privacy work per phase (CLAUDE.md rule 5)

Written into `threat-model.md` / `privacy-model.md` before the phase's code.

| Phase | Model update | Negative tests |
|---|---|---|
| A | Tree custom terms are tree data (RLS); global curation admin-only | Cross-tree term read/write, contributor promoting to global, XSS in labels |
| B | Public reference endpoints only | Rate limit, query abuse |
| C/D | Terms must not reveal hidden people; provisional people private; undo scope | Hidden-path leakage, IDOR on anchor/intermediates, viewer escalation, undo of someone else's records |
| F | Reviewer capability; diffs carry living data; revision binding | Self-approval, branch-scope escape, diff redaction, approving a stale proposal |
| H | ICS tokens | Token reuse after revocation, living birthdays leaking to viewers |
| I | Consent, withdrawal, retention, third-party mentions, external STT | Link reuse/expiry, recording without consent, non-audio upload, withdrawal erases media/transcript/proposals |
| K/M | Export scope and consent | Viewer export, another living person's private data, signed-URL reuse |
| L | Shared devices, local caches | Data left after logout/expiry, other people's data in caches |
| N | Cross-tree linking | Data crossing trees without both admins' consent |

## 7. Open questions (owner decisions)

Recorded in [open-questions.md](open-questions.md) with the defaults proposed in the review:

- **Q13** (existing) is a **public-launch gate**.
- **Q14** Regional kinship vocabularies: Hindi first, then native-reviewed packs prioritised by
  actual user demand.
- **Q15** LGD updates: quarterly, versioned snapshots; historical and unlisted places stay editable.
- **Q16** Panchang engine: select and legally review a supported engine before enabling automated
  lunar reminders.
- **Q17** Voice processing: self-hosted by default; external only with informed opt-in; documented
  retention and deletion.
- **Q18** Biodata: deferred, consent-first, no compatibility scoring.
- **Q19** Product name: keep "Vanshavali" in the repo and app; decide whether "Parampara" is a
  separate heritage brand before changing public branding. *vanshavali.net.in* is another product;
  check trademark/domain overlap before a public launch.

## 8. Revision history

- **Rev 1 (4 Nov 2026):** audit and phases A–O.
- **Rev 2 (4 Nov 2026), after design review of PR #27:** Smart Add requires a preview and explicit
  confirmation, with provisional people visibly distinct (D); master data split into controlled
  enums and extensible vocabularies with a transition plan (A); age order compares the correct pair,
  supports uncertainty and family-confirmed order (C); kinship terms no longer set identity fields
  (D); `FAMILY_CONFIRMED` dropped in favour of a separate review state, and proposals bound to a
  base revision (F); staged LGD import with provenance checks and benchmarks (B); calendar no longer
  claims to resolve Q6 (H); consent, retention and third-party rules for voice (I); exports governed
  by the privacy serializer and consent, not watermarks (K); shared-device controls (L); releases
  R1–R5 and acceptance criteria (§4–5); Q13 made a public-launch gate.

Competitor feature claims in the original review were not tested, either by the reviewer or in this
audit. The features worth adopting are in the phases above.
