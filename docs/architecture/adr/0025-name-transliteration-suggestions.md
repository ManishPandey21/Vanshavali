# ADR-0025: Name transliteration suggestions

- Status: Accepted · Date: 2026-11-06 (accepted as proposed, including both open points) · Issue: #34 (R1)
- Relates to: ADR-0007 (search normalisation), ADR-0008 (GEDCOM `TRAN`), ADR-0009 (provenance; no
  external AI by default), ADR-0018 (reference data packs), ADR-0003 (names as claims)
- Plan: [india-master-data-and-smart-forms-plan.md](../india-master-data-and-smart-forms-plan.md),
  Phase D "Progressive form: name (with transliteration suggestion, original kept)"

## Context
Families write the same name in two scripts: "Sunita Sharma" and "सुनीता शर्मा". Today a user can
add a second name record of type `transliteration` by hand, and search already folds every script
to a Latin key (`textnorm.romanize`, ADR-0007). What is missing is a **suggestion while typing**:
"In Devanagari: सुनीता शर्मा — add as another name?".

The installed `indic-transliteration` library is the obvious engine, but it is built for scholarly
schemes, not for how Indian names are actually spelt. Measured on this codebase (6 Nov 2026):

| Input | Library output | What a family writes |
|---|---|---|
| Sunita (OPTITRANS → Devanagari) | सुनित | सुनीता |
| Sharma | शर्म | शर्मा |
| Ramesh | रमेश् (stray halant) | रमेश |
| Iyer | इयेर् | अय्यर |
| रमेश (Devanagari → ITRANS, folded) | ramesha | Ramesh |
| मोहन | mohana | Mohan |
| आरव | arava | Aarav |

Casual romanisation drops vowel length (a/ā, i/ī), retroflexes (t/ṭ) and the Hindi inherent vowel
(schwa) rules, so the mapping is **one-to-many in both directions**. A suggestion engine can help,
but it must never decide.

## Decision

### 1. Suggestions only; the typed name is never changed
- A suggestion is shown, never applied. The value the user typed is saved exactly as typed.
- Accepting a suggestion adds a **separate `name_record`** for the same person:
  - `type = transliteration`, `is_preferred = false`;
  - `script` and `language` set from the target (e.g. `Deva`/`hi`, `Latn`/`en`);
  - the same name parts as the source (given name ↔ given name, surname ↔ surname).
- `romanized_value` on the typed record stays a user-entered field. The engine never writes it.
- Dismissing a suggestion stores nothing.

### 2. A local, deterministic engine: lexicon first, Hindi rules second
- **Lexicon:** a reviewed list of common given names and surnames as pairs (Latin spellings ↔
  Devanagari), each with source, licence and reviewer. It is versioned and ships with the code
  (`backend/app/modules/translit/lexicon/hi.json`), like ADR-0018's packs. A name in the lexicon
  returns its listed forms (several spellings where they exist, e.g. Laxmi/Lakshmi → लक्ष्मी).
- **Rules** (only when a token is not in the lexicon), on top of `indic-transliteration`:
  - Latin → Devanagari (Hindi orthography): no word-final halant (रमेश, not रमेश्); word-final
    "a" → ा (Sharma → शर्मा); ambiguous vowel length produces **alternatives**, not a guess
    (Sunita → सुनीता, सुनिता).
  - Devanagari → Latin (casual Hindi romanisation): delete the final inherent vowel (रमेश → Ramesh)
    and the medial one in the common C-V-C-a-C-V pattern; fold long vowels, except a word-initial
    आ, which is spelt "Aa" (आरव → Aarav); title-case each token.
- **Output:** at most **3 candidates**, ordered lexicon before rules. Each one says *how* it was
  produced (`lexicon` or `rules`), so the UI can label rule-based ones as "a possible spelling".
- **Determinism:** the same input and engine version always give the same candidates. The engine
  is identified as `vanshavali-translit` plus a version, e.g. `hi-Latn/1`, and the lexicon version.

### 3. Scope of version 1
- **Devanagari ⇄ Latin** for Hindi only, matching the UI languages (Q8).
- Other Indic scripts (Bengali, Tamil, Telugu…) are **not** suggested in v1: their romanisation
  conventions differ and need their own reviewed lexicons and rules. That belongs with the regional
  vocabularies (Q14). Search across them is unchanged (ADR-0007).
- **Names only**: given name, surname and the other name-part fields. Not places (Phase B and
  ADR-0019 handle historical names), not free text, not heritage values.

### 4. API
`POST /api/v1/transliterate` with `{text, target_script: "Deva" | "Latn", source_script?}`
returns:

```
{candidates: [{text, method: "lexicon" | "rules"}],
 engine: "vanshavali-translit",
 version: "hi-Latn/1",
 lexicon_version: "..."}
```

- **Access:** signed-in users only. It is not tree-scoped, because it reads no tree data.
- **Limits:** text ≤ 200 characters; rate-limited per user (the existing limiter, ADR-0005);
  responses are not cached by the server.
- **Privacy:** the text is **not logged and not stored**, and the request body is excluded from
  access and error logs. The text never leaves our servers (§6).
- The SPA calls it after typing pauses (debounced, ~400 ms) and cancels stale requests.

### 5. Provenance of an accepted suggestion
The new name record is a claim like any other (ADR-0003), recorded as calculated and then
confirmed by the user (ADR-0009 vocabulary):
- `prov_origin = calculation`;
- `prov_algorithm = "vanshavali-translit hi-Latn/1 (lexicon|rules)"`;
- `prov_confirmed_by` = the user, `prov_confirmed_at` = now;
- `evidence_status = USER_ASSERTION`. A suggested spelling is never evidence of anything.

The UI can then show "spelling suggested, confirmed by you". GEDCOM export needs no change: a
name in another script is already written as `TRAN` under the host name (ADR-0008).

### 6. What it never does
- **No external services.** Google Input Tools, BHASHINI and similar APIs would send relatives'
  names outside our infrastructure (ADR-0009 §5, DPDP). A later provider would need an amendment
  and a per-tree opt-in.
- **No learning from families.** The engine never learns from names other families enter. That
  would leak one tree's names into another tree's suggestions. The lexicon changes only through
  code review.
- **No inference.** A transliteration never sets or changes sex, gender, community, region or any
  other field. A name's script says nothing about a person.

### 7. Interface
Suggestions appear in the person form, the name editor and Smart Add's details step:
- **Where:** under the name fields, as "In Devanagari: सुनीता शर्मा" with an **Add as another name**
  button, alternatives as further buttons, and **Dismiss**.
- **Accessibility:** keyboard reachable, announced politely (`aria-live="polite"`), never moving
  focus.
- **Language:** each candidate is marked up with its `lang` and script so it renders with the right
  font. Shown in English and Hindi UI.
- **Progressive disclosure:** nothing appears until a name part has at least two letters. Nothing
  appears when the typed text is already in the target script.

### 8. Native-Hindi review (the rest of #34)
- The review stays a human task under `docs/localization/hindi-review-checklist.md`.
- The pack generator (`ops/i18n/hindi_review_pack.py`) is re-run, so the pack includes every R1
  string in the locale files and `kinship.ts`: Smart Add, "To complete", age-aware kinship words and
  basis notes. It reads neither the master-data packs nor the lexicon yet, so it is extended with two
  new files:
  - the Hindi labels of the master-data packs (`backend/app/modules/masterdata/packs/*.json`);
  - the transliteration lexicon, because a wrong pair would be suggested to every family.
- Sign-off is recorded only in the checklist's table, with the reviewer's name and date. No string
  counts as reviewed without it.

## Consequences
- No schema change. It uses the existing `name_record` columns, `NameType.TRANSLITERATION` and the
  provenance columns.
- New module `app/modules/translit`: engine, lexicon and router. A threat-model row covers the
  endpoint: abuse as a free service, logging of names, and lexicon poisoning.
- Search improves for free: an accepted Devanagari name is indexed like any other.
- Quality depends on the lexicon. The rules cover names outside it but are labelled as "possible".

## Alternatives considered
- **Use `indic-transliteration` as is.** Rejected: the measurements above (missing vowel signs,
  stray halants, schwa) would mislead families.
- **A browser-only library (Sanscript.js or similar).** Rejected: the same scholarly-scheme
  problems, plus a second copy of the rules to keep in step with the server's.
- **ICU / CLDR transforms (PyICU).** Rejected for v1: they produce ISO 15919-style scholarly
  romanisation, not the casual spelling families use. ADR-0007 already lists ICU as a possible
  search upgrade.
- **AI4Bharat IndicXlit, self-hosted.** Deferred. It is better on unseen names and openly licensed,
  but a PyTorch model adds hundreds of MB and CPU latency to every keystroke pause. Its provenance
  is a model version rather than reviewable rules. The API and provenance fields above allow it as
  a later engine version behind the same interface, after its own amendment.
- **External transliteration APIs.** Rejected (§6).
- **Write the suggestion into `romanized_value` of the typed record.** Rejected: provenance is
  recorded per record, so a calculated value would sit inside a manually entered record with no
  trace. A separate record keeps "typed" and "suggested, confirmed" apart, and exports as `TRAN`.

## Stress test (questions this ADR must answer)
1. *Can a suggestion change what the user typed?* No (§1). The suggestion is a new record, created
   only on an explicit click.
2. *Can one family's names reach another family?* No (§6). There is no learning, no shared cache
   and no logging. The lexicon is reviewed code.
3. *What if the engine is wrong?* The user sees at most three labelled candidates and can dismiss
   them. An accepted wrong spelling is an ordinary name record: editable, deletable, and never
   evidence.
4. *Does it work offline or when the endpoint is down?* The form works exactly as today and no
   suggestion appears. Nothing depends on it.
5. *Does it infer identity?* No (§6). It reads only the name text it is given.
6. *Can the endpoint be abused?* Only signed-in users, a size limit and a rate limit. It returns no
   tree data and stores nothing.
7. *Who decides the lexicon?* Code review, with a source, licence and reviewer per entry, and a
   native-speaker sign-off (§8).
8. *What about names that are not Hindi?* v1 makes no suggestion for other scripts rather than a
   bad one (§3).

## Open points for the reviewer
- **Lexicon source.** Proposal: start from a small hand-curated list of about 300 common North
  Indian given names and surnames, written for this project (no licence issue). Reviewed by the
  same native speaker as §8, and grown from support feedback, never automatically.
- **Medial schwa deletion.** The proposed rule is a known heuristic with exceptions (compounds). It
  is acceptable *because* candidates are labelled "possible spelling", and the lexicon overrides it.
