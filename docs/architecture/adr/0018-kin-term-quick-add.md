# ADR-0018: Adding relatives by Indian kin term ("quick-add")

- Status: Proposed · Date: 2026-10-06
- Relates to: ADR-0003 (relationship model), ADR-0006 (authorisation and privacy), ADR-0019
  (reference vocabularies, which hold the kin-term table)
- Design reference: [searchable-fields-catalogue.md](../searchable-fields-catalogue.md) §4

## Context
Indian families think in kin terms, not graph edges. Hindi alone distinguishes father's elder
brother (*Tau*) from father's younger brother (*Chacha*), father's sister (*Bua*), mother's brother
(*Mama*) and mother's sister (*Mausi*), and names in-laws by side and seniority (*Jeth* / *Devar*,
*Jethani* / *Devrani*, *Nanad*, *Saala*, *Saali*). Today a user who wants to add "my Chacha" has to
work out the path ("add my father → add his sibling") and run `POST /people/{id}/relatives` once per
step. People get it wrong, add the uncle as a sibling of the user, or give up.

Constraints from ADR-0003:

- Only **primitive typed edges** are stored (parent types, union types, sibling, other). Kin terms
  are presentation (`frontend/src/lib/kinship.ts` derives Hindi terms from a relationship chain).
- Siblings are **derived from shared parents**. An explicit `sibling` edge is only for unknown
  parents.
- **Nothing is inferred.** That covers relative age, sex, unions and heritage.

What is missing from the model:

1. **Relative seniority.** *Tau* vs *Chacha* depends on whether the uncle is older or younger than
   the father. Birth dates are often unknown, and the model has nowhere to record "elder than
   father" without them. `kinship.ts` therefore shows both terms ("चाचा / ताऊ").
2. **Missing intermediate people.** Adding a *Chacha* when the father isn't in the tree yet needs a
   person for the father. Adding a *Mausa* needs the *Mausi*.

## Decision

### 1. Kin terms are reference data that expand into primitive paths
A `kin_term` vocabulary (ADR-0019) lists each term with:

- `code`, English label, Hindi label (others later), aliases (*chacha*, *chachaji*, *kaka*, *चाचा*).
- `path`: an ordered list of steps from the anchor person. Each step is one of `parent`, `child`,
  `sibling` or `spouse`. A step may carry `sex` (the sex of the person reached) and `seniority`
  (`elder` / `younger`, relative to the person *before* that step).
  For example *Tau* = `[parent·male, sibling·male·elder]`, *Chachi* =
  `[parent·male, sibling·male·younger, spouse·female]`, and *Saala* = `[spouse·female, sibling·male]`.
- `sex_hint` for the new person, used only to **pre-fill** the form. The user can change it.
- Regional variants (*Kaka* in Marathi and Gujarati, *Chittappa* in Tamil) are separate terms with
  the same path and a `region` tag, never a merged label.

The stored data stays primitive edges only. **No kin term is ever persisted as a relationship
type.** Removing or renaming a term never changes the tree.

### 2. One server-side, atomic endpoint
`POST /api/v1/trees/{tree_id}/people/{anchor_id}/relatives/by-kin-term` with:

```
{ kin_term: "chacha",
  person: { existing_person_id } | { new_person: PersonCreate },
  seniority: "elder" | "younger" | "unknown",      // only for terms whose path has a seniority step
  intermediates: { "<step index>": existing_person_id | "create" },  // optional, see below
  dry_run: bool }
```

The server walks the path from the anchor:

- **Resolve each intermediate person.** At step *i* it looks for existing people who satisfy the
  step: for a parent step with `sex: male`, it looks for the anchor's parents recorded as male.
  - **Exactly one candidate**: use it.
  - **Several** (two recorded fathers, biological and adoptive): `409 kin_path_ambiguous` with the
    candidates. The client asks the user and resends with `intermediates[i]` set.
  - **None**: `409 kin_path_incomplete`, naming the missing step ("father not recorded"). The client
    offers "Also add father". Resending with `intermediates[i] = "create"` creates a **minimal
    person**: no name required, `profile_status = unknown`, display label "Father of ‹anchor›". This
    person is a normal person that can be edited, merged (ADR merge) or erased.

  The server never creates intermediates silently.
- **Write edges with the existing service functions** (`create_person`, `create_relationship`,
  `add_relative`), so cycle checks, union validation, provenance, audit and privacy defaults behave
  exactly as for manual entry.
  - A `sibling` step reaches the sibling **through the shared parent**: the new uncle becomes a
    `biological_parent` child of the grandfather when the grandfather is resolved or created. An
    explicit `sibling` edge is written only when the user declines to create the shared parent.
  - A `spouse` step uses the existing union rules (`union_order`).
  - A `child` step whose parent has exactly one union attaches the child to that union. With more
    than one union, the server returns `409 kin_path_ambiguous`.
- **Atomic.** Everything happens in one transaction. A conflict, a permission failure or a cycle
  rolls back the whole request, so the tree never ends up half-built.
- **`dry_run: true`** returns the plan (which people would be reused, created and linked) without
  writing anything. The UI shows it as a confirmation ("Add Ramesh as father's younger brother.
  Ramesh will also be recorded as a child of Shivnath (grandfather).").
- The response lists every created person and relationship id. The audit log records one
  `relative.quick_add` event that groups them, which is what a later "undo" uses.

### 3. Relative seniority is a recorded, disputable fact
- If both siblings have birth dates with day precision, seniority is read from the dates and
  nothing is stored.
- Otherwise the answer to "Is he elder or younger than ‹father›?" is stored as an **assertion**
  (ADR-0003): subject = the new person, a new attribute `relative_seniority`, value
  `{relative_to: <person id>, value: "elder" | "younger"}`, `evidence_status = USER_ASSERTION`,
  with the person's own privacy level.
  - It can be disputed, cited or superseded like any other fact.
  - **"Don't know" stores nothing**, and the display keeps showing both terms.
- Seniority is never derived from names, from the order in which people were entered, or from
  relatives' ages.
- When birth dates later contradict an assertion, the conflict is shown (like birth conflicts),
  never auto-resolved.
- `kinship.ts` (and its server equivalent, if one is added) uses dates first, then the assertion,
  then shows both terms.

### 4. Authorisation and privacy
- The caller needs `person.write` on the anchor (with branch scope) and on every existing person the
  path links to, the same as `_require_rel_write` today.
- Minimal intermediate people get the tree's default privacy level and `profile_status = unknown`.
  The privacy layer treats `unknown` as possibly living, so they are hidden from public views like
  living people.
- A `409` that lists candidates only includes people the caller can see. People the caller can't
  see are neither listed nor counted. The response must not reveal that a hidden father exists.
  A hidden match is treated as "no candidate", and creating a duplicate is acceptable; merge
  handles it later.
- Kin-term labels are rendered from vocabulary data and never from user input. No new upload or
  download surface.

### 5. Scope of the first version
- Paths of up to three steps: grandparents, uncles and aunts and their spouses, nephews and nieces,
  grandchildren, and in-laws (*Sasur*, *Saas*, *Jeth*, *Devar*, *Nanad*, *Saala*, *Saali*, *Jija*,
  *Bhabhi*, *Damad*, *Bahu*).
- *Samdhi* / *Samdhan* (a child's parents-in-law) are out of the first version. They are a
  four-step path with no blood or marriage link to the anchor and are better added from the
  child's spouse.
- Cousin terms (*chachera bhai* …) come after the path engine has proved itself.

## Consequences
- Users add relatives the way they talk about them, and the stored graph stays canonical and
  GEDCOM-exportable (only primitive edges are written).
- New: one endpoint, one assertion attribute (`relative_seniority`, an Alembic migration that
  widens the `HeritageAttribute` check constraint), the `kin_term` vocabulary (ADR-0019), and an
  update to `domain-model.md`.
- More empty "minimal" people will appear. The people list and tree must label them clearly
  ("Father of …, details unknown") and the merge tool must find them as duplicate candidates.
- The two `409` replies make the client a small state machine (ask, then resend). `dry_run` keeps
  this predictable and testable.
- Tests required:
  - Path expansion for every term in the vocabulary.
  - Atomic rollback on a mid-path failure.
  - No inference: a test that "unknown" seniority stores nothing and that sex is only pre-filled.
  - IDOR/BOLA: anchor or intermediate in another tree, or not writable by the caller → 404/403
    without leaking.
  - Hidden-candidate non-disclosure.
  - Playwright: add *Chacha* with no father recorded → confirm → tree shows father and uncle.

## Alternatives considered
- **Store kin terms as relationship types** (`type = chacha`). Rejected: it duplicates what the
  graph already implies, drifts when edges change (exactly the prototype bug ADR-0003 fixed), can't
  be exported to GEDCOM, and multiplies across languages.
- **Orchestrate on the client with several existing calls.** Rejected: not atomic (a failure leaves
  half a branch), it repeats the path logic in every client, and the client can't safely decide
  which hidden people exist.
- **Store seniority as `birth_order` on parent→child edges.** Rejected for now: it needs the full
  ordering of all siblings, which families rarely know, while "elder than father" is a single
  comparison they do know. An assertion records exactly what was said, with evidence, and doesn't
  block a later birth-order field.
- **Infer *Tau* vs *Chacha* from dates of birth entered with year precision only.** Rejected:
  year-only and `circa` dates often overlap, so an inferred term would be confidently wrong.
  Day-precision dates are required before dates decide.

## Open questions
- Which regional term sets ship after Hindi: Marathi/Gujarati (*Kaka*, *Atya*), Tamil (*Periyappa*
  / *Chittappa*), Bengali (*Jethu* / *Kaku*), Punjabi (*Taya* / *Chacha*)? This depends on Q8
  (UI languages) in `open-questions.md`.
- Should the vocabulary's matrilineal terms (*Karanavar*, tharavad roles) also become quick-add paths,
  given branch-level `descent_rule` (Q5)?
