# ADR-0026: Cultural depth: pravara, devak and kuladevata, regional kinship packs, family traditions

- Status: Proposed · Date: 2026-11-08 · Release: R4
- Relates to: ADR-0018 (master-data vocabularies; this ADR completes its phase-A transition),
  ADR-0020 (kinship terms, age order), ADR-0003 (heritage as claims, no inference), ADR-0006
  (privacy, field groups), ADR-0021 (review, revisions), ADR-0004 (documents), Q4, Q14
- Plan: [india-master-data-and-smart-forms-plan.md](../india-master-data-and-smart-forms-plan.md),
  release R4: phase G, the rest of phase A, regional packs of phase C

## Context
R1 to R3 built the plumbing: vocabularies (ADR-0018), places (ADR-0019), kinship with age order
(ADR-0020) and family review (ADR-0021). R4 is about *content* families care about and the app
cannot show well yet:

- **Gotra, kula and kuladevata/kuladevi exist as suggestion lists.**
  - The two deity lists are empty and only grow inside each tree.
  - A family's own entry can never become a suggestion for anyone else: ADR-0018 left promotion
    for "later, outside the app".
  - Pack terms carry no `status` yet, although ADR-0018 defined one.
- **Pravara, devak, ancestral occupation and family languages are missing** (ADR-0018 table:
  "later, phase G").
  - Pravara is tied to gotra, but the association differs by tradition, and published lists
    disagree.
- **Kinship words are hard-coded in the frontend, in Hindi only** (`kinship.ts`).
  - Marathi, Bengali, Tamil, Telugu, Gujarati and Punjabi families each use different words.
    Many words depend on whether the speaker is male or female, and on who is older.
  - Some families use their own word ("Bhayo" for Bhabhi).
  - Q14's answer: Hindi first, then regional packs by demand, each a draft until a native speaker
    reviews it.
- **Traditions have no home.** Rituals, customs, songs, recipes and stories can only be squeezed
  into a heritage claim's free text (`family_traditions`) or a document.
- **Old static lists are still in use.** The frontend still ships `src/data/masterData/*` as
  fallbacks; phase A step 3 (switch every form, then delete them) is not done.

Hard constraints carried from earlier ADRs:
- **Suggestions only, never inference.** A gotra never implies a community, region or religion,
  and a kinship word never sets sex or age.
- **No caste or religion lists** (Q4).
- **The stored value is what the family chose or typed.**
- **A word is shown to families only once a native speaker has reviewed it.**

## Decision

### 1. Scope of R4
- **In:**
  - pravara linked to gotra;
  - devak, ancestral occupation, family languages;
  - surname history, as names with a period;
  - kuladevata/kuladevi linked to a temple place;
  - sharing a family's entry into the common lists;
  - regional kinship packs and per-family words;
  - a traditions archive;
  - finishing ADR-0018's transition: every form on the service, static lists deleted.
- **Out:**
  - computing compatibility of any kind (Q18);
  - inferring any attribute from another;
  - caste, jati or religion suggestion lists (Q4);
  - automatic transliteration of kinship words beyond what a pack lists;
  - audio and video for traditions, beyond attaching existing documents (that is phase I, oral
    history).

### 2. New heritage attributes
New `HeritageAttribute` values. They are controlled names, so they need a migration of the check
constraint:
- **`devak`:** the devak (totem/emblem, mainly Maharashtrian families). Vocabulary `devak`, which
  starts empty and grows from families (§4).
- **`ancestral_occupation`:** suggestions from the existing `occupation` vocabulary. Free text is
  always allowed.
- **`family_language`:** multi-valued, from the closed `language` vocabulary. The existing
  `language_traditions` stays as free text for notes such as "Awadhi at home, Hindi outside".

All of them are `heritage` field-group data (ADR-0006), with the same privacy, evidence and
provenance as every claim. They are offered in the heritage editor only. Nothing is filled in.

**Surname history uses names, not a new attribute.** A former surname is a `name_record` with
`type = historical` and a `date_range` ("Sharma until 1950, then Upadhyay"). That keeps it in
search, GEDCOM and history. The person page shows those names as a timeline.

### 3. Pravara linked to gotra
- **A new vocabulary, `pravara`,** whose terms name their gotra in `parent_code`. Each pack entry
  carries a `source` (text, edition, page) and a `tradition` scope, because associations vary.
- **Every link starts `draft`.** It becomes `reviewed` only when a cited source and a reviewer are
  recorded in the pack, by code review.
- **Suggestions.** Picking a gotra suggests pravaras **only from reviewed links**, labelled "often
  associated with this gotra; traditions differ". Every pravara stays searchable regardless of
  gotra, and free text is always allowed. A pravara is never filled in from the gotra, and a
  gotra is never inferred from a pravara.

### 4. Families' own entries can become common suggestions (curation)
This applies to kuladevata, kuladevi, devak, gotra and kula entries a family added
(`tree_vocabulary_term`).
- **Sharing is opt-in.** A tree admin may *offer* an entry to the common list: label, aliases, an
  optional temple place name and an optional note. Who offered it and the tree id stay private to
  operators; the shared term never names the family. Offering is a per-entry action, never
  automatic.
- **Operators curate with a CLI.** `python -m app.cli.masterdata offers` lists pending offers and
  merges duplicates ("Khandoba", "खंडोबा", "Khandoba of Jejuri"). Accepting an offer writes it
  into the pack JSON, so promotion happens **by code review**, exactly like every other pack
  change. The next `load` makes it a global term with `status = reviewed`. A system-admin page can
  come later.
- **Promoted entries keep working.** The family's records keep their stored label and code. The
  tree term records the global code it became, and search returns one result, not two.
- **Declining** tells the admin, without a reason that names other families.

### 5. Kuladevata and kuladevi linked to a temple
- A `kuladevata` or `kuladevi` claim may carry a `place_id` (as the ancestral village already
  does) pointing at a tree place of type `temple`. That place may be linked to LGD (ADR-0019).
- The deity and the temple are separate facts: one deity may be worshipped at several temples,
  and a family may name only the deity.
- Global deity terms may carry a well-known temple *name* in `attributes`, as a suggestion only.

### 6. Regional kinship packs (Q14)
- **The data moves to the backend.** The Hindi words leave `kinship.ts` for a pack of the new
  controlled-key vocabulary `kinship_term`. Each term is keyed by:
  - the chain pattern (`father.brother`, `husband.elder_brother`…);
  - the sex of each hop, where it matters;
  - the age order of the relevant pair (ADR-0020's rules, unchanged);
  - the speaker's sex, where the language differs;
  - language and region.

  `/relationship-path` returns `terms: [{lang, region, term, transliteration, alternatives,
  basis, review_status}]`. `kinship.ts` becomes a renderer. Its test matrix moves to the backend
  as a golden test that runs for every pack.
- **Packs:** one per language and region (`kinship-hi-north.json`, `kinship-mr.json`…). Each
  carries reviewer, review date, source and licence.
  - A pack is shown to families **only when `reviewed`**. Draft packs exist only for reviewers,
    behind a reviewer flag.
  - A word missing from a pack falls back to the English description, never to a guess or to
    another language's word.
- **Which word a person sees** follows this order:
  1. the person's own choice of language and region (a user setting);
  2. the tree's default;
  3. the UI language.

  The kinship language is separate from the UI language: the UI stays English and Hindi (Q8),
  while kinship words can be in any reviewed pack.
- **Family words.** A tree, or one branch of it, may record its own word for a term ("Bhayo"
  instead of "Bhabhi").
  - Stored in `kinship_override` (tree-scoped, row-level security): pattern key, language, word,
    optional `branch_id`.
  - Shown first, marked "your family's word", with the pack's word beside it.
  - Requires `FAMILY_WRITE`, and is under review when the tree's policy is `all` (ADR-0021).
- **Nothing about a person is inferred from a word.** A word is chosen *from* the edges and
  sexes already recorded; it never sets them. The speaker's sex comes only from the viewer's own
  claimed profile. Without one, both forms are shown.
- **Which packs ship.** R4 ships the format, the engine, the Hindi (North) pack and the
  pipeline. Each further pack ships when a native reviewer signs it off, in an order the owner
  sets by demand (open point).

### 7. Family traditions archive
- **A new tree-scoped table `tradition_entry`** (row-level security, revision history as in
  ADR-0021):
  - `kind` (controlled): ritual guide, custom, song, recipe, story, other;
  - `title`, `body` (plain text with light formatting, sanitised; at most 50,000 characters),
    `language` and `script`;
  - links to people, events, places and a branch;
  - its own `privacy_level` (default `TREE_MEMBERS`);
  - citations (ADR-0009) and attached documents (photos, scans, recordings already uploaded,
    ADR-0004).
- **Privacy.**
  - Mentioning a living person does not make the entry public.
  - Public (deceased-only) trees never show traditions in R4.
  - The family archive export includes traditions the exporter may see; GEDCOM does not, since
    it has no place for them.
- **Who may change it.**
  - Anyone with `FAMILY_WRITE` may add an entry.
  - Editing someone else's entry follows the tree's review policy, as `all` changes do
    (ADR-0021).
  - The author and admins may withdraw an entry.
- **Search.** Titles and bodies are searchable within the tree (ADR-0007 keys, any script),
  filtered by privacy as every search is.

### 8. Finishing ADR-0018's transition (rest of phase A)
- **Status in packs.** Every pack term carries `status`. The existing gotra, kula, occupation,
  honorific and language terms become `reviewed` once the native-Hindi review (#34) signs their
  labels off, and stay `draft` until then. `draft` terms remain suggestable, labelled "unreviewed
  spelling".
- **Forms.** Every remaining form reads the service through `SmartSelect`: occupation on
  names, honorific, language on names and places, and the heritage editor for every vocabulary
  attribute. Then `src/data/masterData/*` and its fallbacks are deleted.
  - With `VSH_MASTERDATA_ENABLED=false` the fields become plain text inputs; no static list is
    kept.
- **Faster vocabulary reads:** an ETag on `GET /vocabularies/{key}`, and a `scope` filter
  (region or tradition) for gotra and pravara.

### 9. API (all under `/api/v1`, typed, authorised)
- **Offers:** `POST /trees/{t}/vocabularies/{key}/terms/{code}/offer` (tree admin) and
  `GET /trees/{t}/vocabulary-offers` (the offers and their status).
- **Pravara:** `GET /vocabularies/pravara?parent={gotra_code}&reviewed_only=true`.
- **Kinship terms:** `GET /kinship/packs` (reviewed packs; drafts too for reviewers), and
  `GET|PUT|DELETE /trees/{t}/kinship-overrides`.
- **Kinship preference:** `PUT /me/kinship-preference` ({lang, region}) and the tree default in
  tree settings.
- **Traditions:** `GET|POST /trees/{t}/traditions` and `GET|PATCH|DELETE /trees/{t}/traditions/{id}`,
  with cursor pagination, filtered by kind, person, branch and `q`.

### 10. Interface
- **Heritage editor.** Pravara suggestions appear under the chosen gotra with the "traditions
  differ" note. Devak, ancestral occupation and family languages work like the other attributes.
  Kuladevata gets a temple field (a place picker of type temple).
- **Names:** the person page shows former surnames as a timeline.
- **Kinship words:** a language and region choice in the user menu ("Relationship words in…"),
  family words in tree settings, and on the relationship page each term with its basis, "your
  family's word" and "not yet reviewed" labels.
- **Traditions:** a Traditions page (list, filters, editor) and a section on each person's page.
- **Offers:** "Offer to everyone" on a family's own entry, with its status.
- **Standards:** 390 px, accessible, Indic scripts marked with `lang`, English and Hindi UI.

## Consequences
- **One migration, with a downgrade:**
  - new `HeritageAttribute` values (check constraint);
  - offer columns on `tree_vocabulary_term` (`offer_status`, `offered_by`, `offered_at`,
    `offer_note`, `promoted_code`);
  - `kinship_override`, `tradition_entry` and its link tables, all with row-level security;
  - the user's kinship preference and the tree default.
- **New packs:** `pravara` (draft until sourced), `devak` (empty), `kinship_term` (Hindi North,
  moved from the frontend).
- **Kinship moves to the backend.** The resolver gains a backend module with a golden-matrix test
  per pack. The frontend matrix test is kept until the move is verified, then deleted.
- **Threat model:**
  - a new entry for offers (another family's identity reaching the common list; poisoning the
    list);
  - a new entry for traditions (living people's details, privacy, HTML injection, export scope);
  - a new entry for family words (cross-tree leakage).
- **Privacy model:** a section on traditions and on offers.

## Alternatives considered
- **Auto-fill pravara from gotra.** Rejected: associations vary by tradition, and filling in
  would assert something the family never said (plan principle: no inference).
- **One national kinship list, with regional words as aliases.** Rejected: words differ by the
  speaker's sex and age order. Aliases can't carry that, and the wrong regional word is worse
  than an English description.
- **Showing draft kinship packs with a warning.** Rejected for families (Q14). Reviewers see
  them behind a flag.
- **Promoting families' entries automatically once N families use them.** Rejected: it leaks
  how many families use something, invites poisoning, and bypasses review. Offers are explicit,
  and promotion happens by code review.
- **Traditions as documents only.** Rejected: rituals and recipes are text families write and
  edit, need linking to people and places, and must be searchable.
- **Traditions as heritage claims.** Rejected: claims are short values with evidence status; a
  ritual guide is long-form content with its own privacy.
- **A wiki or markdown engine with HTML.** Rejected: injection risk and no need. Plain text with
  light formatting, sanitised.

## Stress test
1. *Can a gotra pick fill in pravara, community or region?* No. Only reviewed pravara links are
   suggested, labelled as associations, and never filled in. Nothing else is suggested from a
   gotra (§3, Q4).
2. *Can one family's kuladevata or devak reveal them to others?* Only if their admin offers it.
   The common term never names the family, and only operators see who offered it (§4).
3. *Can someone poison the common lists?* Offers need a tree admin, a curator and a code-reviewed
   pack change. Nothing reaches other families automatically (§4).
4. *Can an unreviewed regional word reach families?* No. Only reviewed packs are shown. A
   missing word falls back to English, never to a guess (§6).
5. *Does a kinship word infer sex or age?* No. Words are chosen from recorded edges, sexes and
   age order, and the speaker's sex only from a claimed profile (§6, ADR-0020).
6. *Can a tradition entry expose a living person?* It has its own privacy level, follows field
   and person visibility in links, is never public in R4, and is exported only as far as the
   exporter may see (§7).
7. *Can a tradition body carry script or markup?* No. It is plain text with light formatting,
   sanitised on save and rendered as text (§7).
8. *What happens to stored values when a term is promoted, renamed or retired?* Nothing. The
   label is stored and the code keeps resolving (ADR-0018 §6, §4).
9. *What if the master-data service is switched off after the static lists are gone?* Fields
   become plain text. Every stored value still shows, because labels are stored (§8).

## Open points for the reviewer
- **Order of regional kinship packs.** Proposal: the next pack is whichever language has the most
  users with that UI or kinship preference, once a native reviewer is found. Suggested first
  candidates: Marathi, Bengali, Punjabi. The owner decides.
- **Where curation happens.** Proposal: operator CLI plus code review for R4, and a system-admin
  page later. Alternative: an admin page now.
- **Traditions on public trees.** Proposal: never in R4. Alternative: opt-in per entry, for
  entries that name only deceased people.
- **Surname history as names.** Proposal: historical names with a period (no new attribute).
  Alternative: a separate `surname_history` attribute.
