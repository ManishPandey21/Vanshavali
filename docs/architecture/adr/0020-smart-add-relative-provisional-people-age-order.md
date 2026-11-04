# ADR-0020: Smart Add Relative, provisional people and recorded age order

- Status: Accepted · Date: 2026-11-04
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
display name "Unnamed", profile status *unknown*, the tree's default privacy, and no sex unless the
user picked one. The UI marks them with a badge. Adding a name clears the flag. Excluding them from
exports and person counts is a follow-up in R1.

### 5. Recorded age order
New tree-scoped table `relative_age_order(elder_person_id, younger_person_id)`, with `created_by`
as the person who confirmed it,, unique per ordered pair; a reversed pair is rejected. Smart Add writes it for terms
that imply an order (Tau, Chacha, Jeth, Devar) and for an optional "older / younger than …" answer on
Brother/Sister. It is family knowledge and, in Phase C, will take precedence over birth dates when
resolving terms. Row-level security applies.

### 6. Identity is not inferred
The term does not set gender identity. The UI may *offer* sex at birth pre-selected from the term on
the confirmation step; the user can change it or leave it unrecorded. The server only stores what
the client sends.

## Consequences
- One migration (`is_provisional`, `relative_age_order` with RLS, downgrade).
- The calculator now finds explicit siblings. Existing trees with explicit sibling edges will see
  more relationships resolved; no data changes.
- Age order is recorded but not yet used for terms; Phase C will use it.

## Alternatives considered
- **Create provisional grandparents to link a sibling.** Rejected: invents two people the user
  did not ask for.
- **Store the chosen term on the relationship.** Rejected by ADR-0003: terms depend on the viewer.
- **Server-side plan sessions.** Rejected: a stateless plan endpoint re-validated at commit is
  simpler and cannot go stale on the server.
