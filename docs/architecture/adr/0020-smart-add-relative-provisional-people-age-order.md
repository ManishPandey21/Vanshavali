# ADR-0020: Smart Add Relative, provisional people and recorded age order

- Status: Accepted · Date: 2026-11-04 · Amended 2026-11-05 (§4, §6, §7: provisional people's
  visibility, verification and exports; design review of PR #27)
- Relates to: ADR-0003 (relationship model), ADR-0006 (authorisation and privacy), ADR-0011
  (attestation before adding people)
- Plan: [india-master-data-and-smart-forms-plan.md](../india-master-data-and-smart-forms-plan.md),
  release R1, phases C and D

## Context
Today a relative is added from a person's profile as a parent, spouse, child or sibling
(`POST /people/{p}/relatives`). Adding "my Mama" (mother's brother) takes three dialogs, and fails
silently in two ways:

1. A sibling added this way is stored as an explicit `sibling` edge. The relationship calculator
   (`engine.relationship_path`) only walks parent and union edges, so it never finds the
   connection: Mama is not shown as an uncle, or as मामा.
2. There is nowhere to record that an uncle is *older* than the father (Tau) or *younger* (Chacha),
   so Hindi terms always show both ("चाचा / ताऊ").

The plan (rev 2) requires a preview and explicit confirmation before anything is created,
provisional people that are visibly distinct, family-confirmed age order that wins over dates, and
no identity attribute inferred from a kinship term.

## Decision

### 1. Kinship terms are a controlled catalogue of paths
`app/modules/smartadd/terms.py` maps each term code (`mama`, `nani`, `tau`, `bhabhi`, `sasur`…)
to a path of basic hops `(relation ∈ parent|child|sibling|spouse, sex ∈ male|female|any)` and,
where the term implies it, an age order between the new person and the previous person on the path
(`tau` = elder than the father, `chacha` = younger; `jeth`/`devar` relative to the husband). This is
a system-controlled value (ADR-0018 classification: *controlled*), not an editable vocabulary.
Words and translations live in the UI locale files; regional vocabularies and family-preferred
words come with the master-data service later. Nothing called "Mama" is ever stored: only the edges.

### 2. Plan, then commit, then (optionally) undo
- `POST /trees/{t}/people/{p}/smart-add/plan` (no writes): for the term and the choices made so
  far, returns each intermediate step's **visible** candidates, whether a new provisional person may
  be created there, how the new person will be linked, and a preview of every record that would be
  created or linked. A step whose recorded parent is hidden from the viewer reports only that one is
  hidden and does not offer a new provisional parent (that would create a duplicate).
- `POST /trees/{t}/people/{p}/smart-add` with the confirmed choices: one transaction, re-validated on
  the server (people visible and in this tree, choices still match the path, no cycles, the
  two-biological-parent cap, union rules). Returns the created records and an `operation_id`.
- `POST /trees/{t}/smart-add/{operation_id}/undo`: only the user who committed, within 30 minutes,
  once, and only while the created people have no relationships other than those the operation made.
  It deletes the operation's relationships and age-order records and soft-deletes (restorable) the
  people it created. The operation is the commit's audit event (`smart_add.committed`, IDs only).
- `PERSON_WRITE` is required for all three; viewers get 403. Branch-scoped editors are bound by the
  existing relationship write checks.

### 3. Linking a new sibling
When the person the sibling is added to has recorded biological parents visible to the user, the
new person becomes their biological child (with the parents' union, if they have one), so tree views
and the calculator see a real sibling. Otherwise an explicit `sibling` edge is created. The preview
says which. The relationship engine now treats an explicit sibling edge as sharing a virtual parent
(never returned in paths or common ancestors), so explicit siblings resolve to brother, uncle,
cousin and so on. This also fixes siblings added through the existing dialog.

### 4. Provisional people
`person.is_provisional` (boolean, default false). Set only when the user explicitly chooses "add
them as unknown for now" for an intermediate step. A provisional person has no name record, the
display name "Unnamed", profile status *unknown* (so they are protected as possibly living), and no
sex at birth unless the user records one.

Three things are kept apart (amended 2026-11-05):

| Question | Where it lives | Changed by |
|---|---|---|
| How was this person created? | `person.is_provisional`: **origin**, never cleared automatically | nothing; it is provenance |
| Does the profile have enough detail? | derived: *needs details* while there is no name record | adding a name |
| Are their relationships supported? | derived from the existing `relationship.evidence_status`: *verified* when every relationship of the person is `FAMILY_RECOLLECTION`, `SOURCED` or `CORROBORATED` | editing a relationship's evidence |

Adding a name completes the details only; it changes no relationship and verifies nothing. The API
returns `provisional_state` (`needs_details` / `unverified` / `verified`) for provisional people.
The UI shows "To complete" while details are missing and "Not yet verified" once named but
unverified. A provisional person who needs details or is unverified is **pending**.

### 5. Recorded age order
New tree-scoped table `relative_age_order(elder_person_id, younger_person_id)`, with `created_by`
as the person who confirmed it,, unique per ordered pair; a reversed pair is rejected. Smart Add writes it for terms
that imply an order (Tau, Chacha, Jeth, Devar) and for an optional "older / younger than …" answer on
Brother/Sister. It is family knowledge and, in Phase C, will take precedence over birth dates when
resolving terms. Row-level security applies.

### 6. Identity is not inferred
The term sets neither gender identity nor sex at birth (amended 2026-11-05: the UI no longer
pre-selects sex at birth from the term). Sex at birth starts as "Not recorded" for the new person and
for every provisional person, and is stored only if the user enters it. The server only stores what
the client sends.

The chosen term is kept apart from identity: it is turned into edges, recorded in the operation's
audit event (`smart_add.committed`, `term`), and shown in the confirmation; it is not discarded when
sex at birth is unrecorded. The calculator then gives a definite word where the sexes on the path are
recorded and a neutral, uncertain one ("parent's sibling") where they are not; it never guesses.

Candidate lists do not drop a recorded relative because of their sex at birth: sex at birth is not
the family role a term names (someone the family calls "mother" may have another recorded sex at
birth). Relatives whose recorded sex matches the term, or is unrecorded, are listed first. A new
provisional parent is still refused when a recorded parent *could* be the one meant (matching or
unrecorded sex), when a parent is hidden, or at two biological parents, so duplicates stay blocked.

### 7. Who can see a provisional person, and exports (amended 2026-11-05)
Options considered for visibility:

1. **Tree default privacy** (the original §4). Rejected: an unnamed, unverified record would be
   visible to every member, and its existence would show in other people's family views.
2. **A new rule in `can_view_person` keyed on `is_provisional`.** Rejected: a second, parallel
   authorization rule, and it would end the moment the flag changed meaning.
3. **Existing `CUSTOM` privacy plus an access grant** (chosen). `CUSTOM` already means "tree admins
   and explicit grants" (ADR-0006). A provisional person is created at `CUSTOM`, with an
   `access_grant (person, view)` for the user who created them, so the creator can keep completing
   the record. Branch scoping, `PERSON_WRITE` and the relationship write checks apply unchanged;
   only tree admins can change the privacy level or grant others access, through the existing
   endpoints. Undo removes the creator's grant with the people.

**Concealment.** For anyone who cannot see a *pending* provisional person, that person does not
exist: no node, edge, "private relative" placeholder or count in family views, graphs, the fan and
neighbourhood charts, lifespans, relationship paths (not walked through), branch and household
counts, candidate lists or public pages. This is stricter than for other hidden people, whose
existence is shown as an anonymous placeholder: an unnamed, unverified record is not yet a fact
about the family. Once named and verified, a provisional person is an ordinary person at their
privacy level (still `CUSTOM` until an admin changes it), and may appear as a placeholder like any
other hidden relative. Leaving provisional people out of headline person counts for those who *can*
see them, and a "To complete" list, are tracked as R1 follow-ups.

**Exports.** Default GEDCOM and archive exports leave out every pending provisional person, whoever
exports, and the relationships that touch them: no `INDI`, no placeholder, no `FAMC`/`FAMS`
pointing at them, nothing in `canonical-data.json`. A named relative linked only through one (Mama
through an unknown mother) is exported unconnected rather than with an invented parent. The archive
manifest's `counts.excluded_provisional` counts only those the exporter could see, so it reveals
nothing to someone who could not. A verified provisional person is exported like anyone else. An
opt-in "include provisional people" export option is deferred; it would need `PRIVACY_MANAGE` and
would export them as `RESN CONFIDENTIAL` placeholders.

**Residual.** The existing biological-parent cap counts every recorded parent, so linking a third
biological parent to someone with a concealed one is refused with "already has two biological
parents" (no identity, but it shows that a second parent is recorded). Integrity wins here; recording
the claim as `DISPUTED` remains possible.

## Consequences
- One migration (`is_provisional`, `relative_age_order` with RLS, downgrade). The 2026-11-05
  amendment adds no schema: it reuses `CUSTOM` privacy, `access_grant` and `evidence_status`.
- The calculator now finds explicit siblings. Existing trees with explicit sibling edges will see
  more relationships resolved; no data changes.
- Age order is recorded but not yet used for terms; Phase C will use it.

## Alternatives considered
- **Create provisional grandparents to link a sibling.** Rejected: invents two people the user
  did not ask for.
- **Store the chosen term on the relationship.** Rejected by ADR-0003: terms depend on the viewer.
- **Server-side plan sessions.** Rejected: a stateless plan endpoint re-validated at commit is
  simpler and cannot go stale on the server.
