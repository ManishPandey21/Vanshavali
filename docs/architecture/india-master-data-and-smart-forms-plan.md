# Plan: India Master Data, Smart Forms and the next feature wave

Status: **proposed** (audit and plan written 4 Nov 2026, before any code).
Input: an external product review that lists the features shown on the landing page, compares
Vanshavali with Indian and international genealogy platforms, and proposes an India-specific feature
catalogue, master dropdown data and a roadmap. Its recommended first step is "India Master Data Pack +
Smart Add Relative Wizard".

This document (1) checks each claim in that review against the code, (2) lists what is missing, and
(3) sets out a phased plan. It follows the working rules in `CLAUDE.md`: decisions that touch
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
   Choosing "Mama" in Smart Add sets sex = male because the *user* said so, not because of a name.
3. **Every cultural field accepts Unknown, Not applicable and "Add my own".** Custom values are
   stored per tree and never leak into the global catalogue without review.
4. **Privacy-first defaults stay.** New features inherit person privacy, minor protection and RLS.
   Voice notes, biodata and cross-family links are consent-gated.
5. **Proposals before facts.** Speech-to-text, OCR, assistant answers and other families' data enter
   as proposals that a person reviews (CLAUDE.md rule 7, ADR-0009).

---

## 3. The plan

Priorities follow the review's P0/P1/P2, adjusted for what already exists. Each phase is shippable
on its own and ends with lint, typecheck, tests, build, Playwright and the a11y audit green.

### Phase A (P0): India Master Data service — ADR-0018

**Goal.** One versioned, central vocabulary service used by every form.

- **Model (migration, with downgrade).**
  - `vocabulary` (global): `key` (e.g. `gotra`, `kuladevata`, `occupation`, `honorific`,
    `marital_status`, `language`, `record_source`, `property_type`), description, owner, version.
  - `vocabulary_term` (global): stable `code`, `labels` JSONB per language (`en`, `hi`, `ta`…),
    `aliases` (spellings, romanisations), `scope` (regions/traditions it applies to), `parent_code`
    (e.g. pravara → gotra), `source` + `source_url`, `status` (`draft` / `reviewed` / `retired`),
    `valid_from/to`, `updated_at`; history via the append-only audit pattern.
  - `tree_vocabulary_term` (tree-scoped, RLS): a family's own entries and overrides ("Add my own",
    preferred spelling). Promotion to global is a manual, reviewed admin action.
- **API.** `GET /api/v1/vocabularies/{key}?q=&lang=&scope=&parent=` (cursor pagination, ETag,
  long cache), `GET /t/{tree}/vocabularies/{key}` (global ∪ tree terms),
  `POST /t/{tree}/vocabularies/{key}/terms` (contributors), admin endpoints for curation.
- **Seed data packs** (`backend/app/modules/masterdata/packs/*.yaml`, loaded by a CLI importer, each
  with source and licence): honorifics, living status, date accuracy, family branch, relation type,
  household type, marital status, name format, occupation, religion/tradition (suggestions, optional),
  English + 22 Eighth-Schedule languages (with ISO 639 codes and scripts), gotra seed list (the 12 in
  the review plus the existing 20+, with aliases; **pravara links marked `draft` until a source is
  attached**), devak (empty + custom), kuladevata/kuladevi (empty catalogue + custom; grown from
  reviewed submissions), family event types, record type, record source, certainty, verification
  status, document visibility, property type, property relation, nakshatra (27), rashi (12), paksha,
  tithi (30), masa (12, amanta/purnimanta names).
- **Frontend.** `useVocabulary(key)` hook (TanStack Query, long stale time) and one accessible
  `SmartSelect` (combobox: search by label or alias in any script, grouped "Suggested / Your family
  / Other", fixed rows *Unknown*, *Not applicable*, *Add my own…*). Replace the gotra datalist, the
  astrology selects and the free-text occupation/honorific fields. Delete
  `src/data/masterData/*` once the packs replace them (update CLAUDE.md).
- **Tests.** Pack schema validation; label-language parity for `en`/`hi`; tree terms isolated across
  trees (authz + RLS); no inference (extend the gotra test to every cultural vocabulary); SmartSelect
  component tests (keyboard, screen-reader names, Devanagari search); migration round trip.

### Phase B (P0): Indian geography reference — ADR-0019

**Goal.** State → District → Sub-district/Tehsil/Taluka → Village/Town cascade with stable LGD
codes, PIN lookup, historical names and "My village is not listed".

- **Data.** Import the Local Government Directory (states/UTs 36, districts ≈ 780, sub-districts
  ≈ 7,000, villages ≈ 6.5 lakh, urban local bodies, gram panchayats) from data.gov.in (GODL-India
  licence: attribution required) and the India Post PIN/post-office directory. Global, read-only
  tables: `geo_unit` (`lgd_code`, `level`, `parent_lgd_code`, names in English + local script,
  `valid_from/to`, `successor_codes` for splits/renames), `geo_unit_alias`, `pincode_office`
  (PIN ↔ office ↔ district, **many-to-many**; never assume one PIN = one village). Versioned
  snapshots; `app.cli.geo import --snapshot YYYY-MM` is idempotent and reports changes.
- **Link to tree places.** A tree `place` keeps its own record (privacy, as-recorded text,
  historical name) and *optionally* references a `geo_unit` via the existing `lgd_code` column. The
  district/state text fields are filled from the reference but stay editable. Pre-1947 and
  outside-India places stay free text with a historical-name flag.
- **API.** `GET /api/v1/geo/units?level=&parent=&q=` (trigram on names and aliases, any script),
  `GET /api/v1/geo/pincodes/{pin}`. Public reference data, rate-limited, no tree data involved.
- **UI.** `PlaceCascade` component used by the Places page, birth/death/event places, heritage
  "Mool gaon / ancestral village" and property parcels. Tehsil label follows the state
  (Tehsil / Taluka / Mandal / Block). Six-digit PIN field with lookup that *suggests* offices.
- **"Remember my ancestral village".** When a branch or the claimant's father line has an
  `ancestral_village` assertion, Smart Add and the heritage form pre-select it as a **suggestion**
  (visible chip "From the Sharma branch — change"); saving records it as the user's own assertion.
- **Tests.** Import idempotency and change report; cascade queries p95 < 100 ms on the full village
  table; PIN many-to-many; historical place preserved on LGD rename; free-text fallback.
- **Ops.** ≈ 7 lakh rows (< 300 MB with indexes); include in backups; document refresh cadence in
  `docs/operations/`.

### Phase C (P0): Kinship engine v2 — "Relationship in my language" — ADR-0020

**Goal.** Correct regional terms from the viewer's point of view, including elder/younger.

- **Relative age.** Derive elder/younger from birth dates when both are known. When not, allow an
  optional `birth_order` on a person within a sibling set, or a `relative_age` (`elder`/`younger`)
  attribute on a sibling relationship, captured in Smart Add ("Elder brother / Younger brother").
  This is a relationship-modelling change: ADR first, migration with downgrade.
- **Move term resolution to the backend.** A `kinship` module with term tables in the master-data
  service (`vocabulary` key `kinship_term`), keyed on: chain, sex of each hop, relative age where it
  matters, **speaker's sex** where languages differ, language, and region/tradition.
  `/relationship-path` returns `terms: [{lang, term, transliteration, alternatives}]` alongside the
  existing English label and chain. The frontend `kinship.ts` becomes a thin renderer.
- **Coverage.** Every term in the North-Indian diagram supplied with the review (Dada/Dadi,
  Nana/Nani, Tau/Tai, Chacha/Chachi, Bua/Fufa, Mama/Mami, Mausi/Mausa, Didi/Jija, Behen/Behnoi,
  Bhaiya/Bhabhi, Bhai/Bhayo, Bhatija/Bhatiji, Bhanja/Bhanji, Jeth/Jethani, Dewar/Devrani,
  Nanad/Nandoi, Bhai Sahab/Saala/Sahlaj, Saali/Sadhu, Bahu, Damaad, Samdhi/Samdhan, Pota/Poti,
  Nati/Natin), then Marathi, Gujarati, Punjabi, Bengali, Tamil, Telugu, Kannada and Malayalam
  packs, each reviewed by native speakers before `status = reviewed`.
- **Family vocabulary.** A tree (or branch) can pick its preferred word for a term (e.g. "Bhayo"
  vs "Bhabhi", "Mausa" vs "Mausaji"), stored as a tree vocabulary override.
- **"Me" perspective.** If the signed-in user has a claimed profile, profile headers and tree
  nodes show "Your Mama · मामा — mother's brother", with the path on hover/focus; the relationship
  calculator defaults "from" to me. Without a claimed profile nothing is assumed.
- **Tests.** Table-driven engine tests for every diagram term (both speaker sexes, elder/younger,
  unknown age → both alternatives), privacy (a hidden intermediate person must not leak the term's
  path), en/hi snapshot tests.

### Phase D (P0): Smart Add Relative wizard and progressive profiles

**Goal.** "Whom do you want to add?" in one step, with only the information needed now.

- **Wizard.** Primary choices: Father, Mother, Spouse, Son, Daughter, Elder/Younger Brother,
  Elder/Younger Sister; "More relations" lists kinship terms from Phase C in the user's language
  (Dada, Nani, Chacha, Mama, Bua, Mausi, Bhabhi, Jija, Bahu, Damaad…). Each term maps to a *path*
  of basic edges. Step 2 asks for a name (with transliteration suggestion), living status and
  approximate year; everything else is "Add more details" (progressive disclosure).
- **Composite creation API.** `POST /t/{tree}/people/{p}/relatives/by-path` creates the target and
  any missing intermediate people in **one transaction** (e.g. "Mama" with no mother on file creates
  "Mother of Aarav (name unknown)" as an *unnamed placeholder*, marked so the UI can prompt to fill
  it). Re-uses existing intermediates when exactly one candidate exists; asks the user to choose
  when there are several (e.g. two wives); never guesses. Suggests duplicates before creating.
  Placeholder people and their privacy are part of ADR-0020.
- **Progressive person form.** Step 1: name, relation, living status. Step 2 (optional):
  birth year/date accuracy, place cascade, occupation, marital status, honorific, name format and
  name language/script. Heritage, astrology and documents stay in their tabs.
- **Transliteration assist.** Typing "Ramesh" offers "रमेश" (and other scripts the family uses) as an
  extra `name_record` of type `transliteration`; the original spelling is always kept. Start with
  the `indic-transliteration` library already used for search; evaluate BHASHINI as an opt-in
  provider later (external processing needs Q7 consent).
- **Tests.** Vitest for each wizard path; API tests for every term → path mapping, placeholder
  creation, ambiguity (multiple spouses/parents), cross-tree IDs (IDOR), viewer role denied;
  Playwright: "add my Nani from scratch in under 6 interactions" on mobile viewport.

### Phase E (P0): Unknown/custom everywhere and the Hindi pass

- Audit every select in the app for Unknown / Not applicable / Other (a lint test over the form
  components).
- Hindi native review of the new strings (extend `docs/localization/hindi-review-checklist.md`).
- Private-by-default and review controls already exist; Phase F adds the review workflow.

### Phase F (P1): Family-verified ancestry (change proposals and review) — ADR-0021

**Goal.** "When someone proposes a new ancestor or changes a relationship, a designated reviewer
confirms it." This is the deferred PRS §28 collaboration work.

- `change_proposal` (tree-scoped): proposer, target (person/relationship/event/assertion), diff,
  rationale, attached sources, status (`draft → awaiting_review → accepted / rejected / contested`),
  reviewer, comments; tree setting to require review for contributors on ancestors, relationships
  and heritage fields. A new `REVIEWER` capability on roles (RBAC change → threat model).
- Per-fact **certainty** in the review's vocabulary, mapped onto existing `EvidenceStatus`
  (document-supported = SOURCED/CORROBORATED, family-confirmed = new `FAMILY_CONFIRMED`,
  family-reported = FAMILY_RECOLLECTION, estimated = date precision `circa` + USER_ASSERTION,
  disputed = DISPUTED). Challenge a fact → opens a contested proposal.
- Version history per person built from the audit log (read model), with "revert this change".
- Notification centre (in-app) for proposals, comments and reviews.
- Tests: authz matrix (contributor cannot self-approve; branch admin limited to branch), IDOR,
  living-person data in diffs redacted for viewers without access.

### Phase G (P1): Gotra/Pravara/Kuladevata and family traditions

- New heritage attributes: `devak`, `ancestral_occupation`, `surname_history` (or reuse historical
  `name_record`s with a period), `family_language` (multi-valued, from the language vocabulary).
- Pravara suggestions filtered by selected gotra **only from reviewed, sourced links**, always
  editable, with the note "associations vary by tradition".
- Kuladevata/Kuladevi catalogue grown from family submissions (review queue), linked to a temple
  `place` with geography.
- **In-app cultural archive.** `tradition_entry` (tree-scoped): ritual guides, recipes, songs,
  customs, with linked people, events, places, branch scope, privacy and sources. Turns the
  landing-page "Stories, guides & wisdom" into a real family feature.

### Phase H (P1): Indian family calendar — tithi reminders — ADR-0022

- Extend `GenealogicalDate` with an optional lunar component: `masa`, `paksha`, `tithi`,
  `month_convention` (amanta/purnimanta), `region`, and keep the original text. Resolves Q6 for
  Vikram Samvat, Shaka, Bengali, Tamil and Malayalam (Kollam) calendars (year/month/day mapping where
  computable; otherwise stored as recorded).
- A Panchang engine (self-hosted; evaluate Swiss Ephemeris — AGPL or commercial licence — versus a
  permissively-licensed algorithm) that computes the next Gregorian date of a tithi for a location's
  sunrise. Reminder types: solar date, lunar tithi, one-time, custom. Event types Punyatithi and
  Shraddha (Pitru Paksha) added to the event-type vocabulary.
- Family calendar page: month view of birthdays, anniversaries, punyatithis and family gatherings,
  ICS feed per user (private token, revocable).
- Tests: golden tables of tithi → date for several years and cities checked against published
  panchangs; DST-free IST and overseas time zones; adhik masa.

### Phase I (P1): Oral history — "Ask an Elder" — ADR-0023

- `story` (tree-scoped): title, narrator (person), interviewer, recorded date/place, language,
  people tagged, privacy, consent record link; media are vault documents (audio/video).
- In-browser recording (MediaRecorder, Opus; resumable upload; works on low-end Android).
- **Ask an Elder link**: built on the ADR-0011 claim-link infrastructure — a single-purpose,
  expiring WhatsApp link that opens a big-button, one-question page in the elder's language; the
  elder (or a guardian) gives recorded consent before recording. No account needed; no tree access.
- Speech-to-text, self-hosted by default (evaluate AI4Bharat IndicConformer / Whisper for hi, ta, te,
  mr, bn…); BHASHINI as an opt-in external provider per tree (Q7). Transcript → name/date/place
  extraction → `extraction_proposal`s reviewed like OCR proposals. Never writes facts directly.
- Threat model: voice is biometric-adjacent personal data; retention, erasure and "remove me" apply.

### Phase J (P1): Duplicate detection and sources — small extensions

Already implemented; add: duplicate check **inside** Smart Add, match reasons that include LGD
village and parents, and a "possible duplicate" badge on new people.

### Phase K (P1): Family book, PDF and image export

Narrative family book (cover, lineage chapters per branch, person pages with privacy filters, heritage
summary, photos, sources), rendered server-side as a background job (WeasyPrint or headless Chromium,
both with self-hosted Devanagari/Indic fonts), signed download. Printable chart posters reuse the
renderer. Living-person content follows the exporter's view, with an explicit "include living
people" opt-in and a watermark.

### Phase L (P1): Elder-friendly, low-bandwidth mobile

PWA install, offline draft for Smart Add and story recording, image compression before upload, a
"large text / simple mode" toggle, and a data-saver mode that skips thumbnails and animations.
Budget: first load < 200 KB gzipped JS on the tree home route; test on a throttled 3G profile in
Playwright.

### Phase M (P2): Matrimonial biodata — ADR-0024

Consent-first: only the subject (claimed profile) or a guardian of a minor-turned-adult can generate
their own biodata. Field-by-field selection from their profile, heritage and astrology data; family
members' living data included only with their own consent; PDF with watermark and expiry link;
never public, never indexed. **Non-goals:** compatibility scoring, guna milan verdicts or any
caste/gotra matching decision.

### Phase N (P2): Migration map, research assistance, cross-family connections, activity feed

- Ancestral-village migration map: already implemented tile-free; add LGD-coded points and an
  optional self-hosted tile layer.
- Research assistance: links out to FamilySearch India collections and Abhilekh Patal by place and
  period (no scraping, PRS §4).
- **Cross-family connections — ADR required** (privacy/RBAC): link a person to the same person in
  another tree (e.g. the bride's natal family) by mutual admin consent; each tree keeps its own
  data; shared fields are opt-in; revocable.
- Activity feed, reunions and announcements per tree (respecting privacy and branch scope).

### Phase O (P2/P3): Family Knowledge Assistant

Answers questions like "Who was my grandfather's elder brother, where was he born, and which branch
are his children in?" in Hindi, Tamil or English.

1. First a **deterministic** query layer: parse a kinship phrase into a path using the Phase C term
   tables, run it through the existing engine and privacy filter, highlight the path in the
   relationship web. No AI needed for most questions.
2. Optional LLM layer (self-hosted by default; external only per Q7 consent) that turns free
   questions into those structured queries and phrases the answer **only** from returned, visible
   records, with citations. When data are missing it offers "Ask a relative" (Phase I link) instead
   of guessing.

---

## 4. Roadmap summary

| Priority | Phase | Delivers | ADR | Depends on |
|---|---|---|---|---|
| P0 | A Master data service | Central versioned vocabularies, SmartSelect with Unknown/NA/custom | 0018 | — |
| P0 | B Geography reference | LGD cascade, PIN lookup, historical names, ancestral-village suggestion | 0019 | A |
| P0 | C Kinship engine v2 | Elder/younger, full North-Indian set, regional packs, "your Mama" | 0020 | A |
| P0 | D Smart Add + progressive forms | One-step "Add my Nani", placeholders, transliteration assist | 0020 | A, C (B optional) |
| P0 | E Unknown/custom audit, Hindi review | No blocked users; reviewed strings | — | A |
| P1 | F Family-verified ancestry | Change proposals, reviewer role, challenges, history | 0021 | — |
| P1 | G Heritage + traditions | Devak, pravara-by-gotra, kuladevata catalogue, in-app cultural archive | — (extends 0003) | A, B |
| P1 | H Family calendar | Tithi dates and reminders, Punyatithi/Shraddha, ICS | 0022 | A |
| P1 | I Oral history | Stories, recording, Ask-an-Elder link, STT → proposals | 0023 | F helpful |
| P1 | J Duplicates in Smart Add | Fewer duplicates at entry | — | D |
| P1 | K Family book | PDF/print family book | — | — |
| P1 | L Low-bandwidth mobile | PWA, offline drafts, simple mode | — | D, I |
| P2 | M Biodata | Consent-first biodata PDF | 0024 | A, G |
| P2 | N Map, research links, cross-family, feed | Growth and engagement | new ADR for cross-family | B, F |
| P2/P3 | O Knowledge assistant | Ask questions in your language | new ADR (AI) | C, F |

**Recommended first slice** (agrees with the review): Phase A + the kinship term data from Phase C +
Phase D, delivered as one milestone ("Master Data Pack + Smart Add Relative"), with Phase B started
in parallel because the LGD import is independent.

## 5. Security and privacy work per phase (CLAUDE.md rule 5)

| Phase | Threat-model / privacy-model update | Negative tests |
|---|---|---|
| A | Tree custom terms are tree data (RLS); global curation is admin-only | Cross-tree term read/write, contributor promoting to global, XSS in labels |
| B | Public reference endpoints only; no tree data | Rate limit, query abuse (wildcard scans) |
| C/D | Kinship terms must not reveal hidden intermediate people; placeholder people are living-by-default and private | Hidden-path leakage, IDOR on anchor/intermediate IDs, viewer escalation |
| F | Reviewer capability; diffs carry living data | Self-approval, branch-scope escape, diff redaction |
| H | ICS feed tokens | Token guessing/reuse after revocation, living birthdays in feed for viewers |
| I | Voice recordings, elder consent, external STT | Link reuse/expiry, recording without consent, upload of non-audio, erasure removes media and transcripts |
| K/M | Exports of living people | Export by viewer, biodata of another living person, signed-URL reuse |
| N | Cross-tree linking | Data flowing across trees without both admins' consent |

## 6. Open questions to add (owner decisions)

- **Q14** Which regional kinship vocabularies after Hindi, and who reviews them?
- **Q15** LGD/India Post refresh cadence, and whether pre-1947 district boundaries are needed.
- **Q16** Panchang engine licence (Swiss Ephemeris AGPL vs commercial vs own implementation).
- **Q17** Speech-to-text: self-hosted only, or BHASHINI opt-in? Retention period for raw audio.
- **Q18** Is matrimonial biodata in scope at all for the pilot audience?
- **Q19** Product name: the review calls the product "Parampara"; the repo, UI and domain use
  "Vanshavali". Confirm the brand before new marketing copy is written.

## 7. Notes on the review's competitor list

- The review lists *vanshavali.net.in* as a competitor. That is a different product from this
  repository; check trademark/domain overlap before a public launch.
- Competitor feature claims were not tested by the reviewer or in this audit. Features worth
  adopting are already reflected in the phases above (relationship explanation → C, cross-family
  links and structured cultural fields → G/N, WhatsApp voice notes → I, activity feed → N, simple
  cultural forms → A/D, transliteration and printable designs → D/K, duplicate suggestions → J,
  evidence-backed research → F, review and approval → F).
