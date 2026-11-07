# ADR-0021: Change proposals, family review and duplicates at entry

- Status: Accepted · Date: 2026-11-07 (accepted as proposed, including the four open points) · Release: R3
- Relates to: ADR-0003 (relationships as typed claims), ADR-0006 (roles, branch scope, field
  redaction), ADR-0009 (provenance; proposals before canonical data), ADR-0011 (attestation),
  ADR-0020 (Smart Add, provisional people), ADR-0019 (LGD place links)
- Plan: [india-master-data-and-smart-forms-plan.md](../india-master-data-and-smart-forms-plan.md),
  release R3, phases F and J

## Context
Anyone with write access changes the tree at once. A cousin with the Contributor role can rename
a great-grandfather, re-parent a branch or delete a heritage claim, and nobody else sees it until
they notice. Families asked for "someone checks before it changes", and the plan's R3 promise is:
*family members can propose, review and challenge changes; stale approvals impossible.*

What exists today:
- **Writes.** Roles and branch-scoped writes (ADR-0006) decide who may change what, but every
  write is final.
- **One review pattern.** OCR output already goes propose → review → apply
  (`extraction_proposal`, ADR-0009).
- **No revisions.** No record has a revision number, so nothing can tell that a fact changed
  between "I reviewed this" and "apply it".
- **History.** The audit log records *who changed which fields*, never the values (by design: it
  must not hold sensitive data). So it cannot show a person's history or undo a change.
- **Notifications.** There are reminders (ADR-0016) but no in-app notifications.
- **Duplicates.** A scorer exists (`search/duplicates.py`, PRS §24) but runs only on the Duplicates
  page. Smart Add can create a person who is already in the tree.

## Decision

### 1. When a change needs review
- **A tree setting, `review_policy`**, chosen by an owner or family admin:
  - `off` is the default, and the default for every existing tree, so nothing changes until a
    family opts in;
  - `structure` covers relationships and heritage claims;
  - `all` covers those plus people's names, vitals and other facts.
- **Who is affected.** Under a policy, members whose roles do not include a reviewing permission
  (§4) **propose** instead of writing. That means contributors, researchers and branch admins
  outside their branch. Owners, family admins and reviewers write directly. Their writes are still
  recorded as revisions (§3), so history and revert work for everyone.
- **What counts as a change.** Changing or deleting an existing fact, and linking two existing
  people. **Adding new people** (Add person, Smart Add, add relative) stays direct: it adds new
  claims and overwrites nothing, and Smart Add already shows a preview the user confirms
  (ADR-0020).
  - A Smart Add plan that links a new person *to an existing person's union* is adding.
  - A plan that links **two existing people** is a change: under a policy, its Confirm becomes
    *Send for review*, and the whole operation becomes one proposal.
- **Own work.** A contributor may still edit or delete their own records until someone has
  reviewed them. Nobody else's work is touched.
- **The server decides.** The direct write endpoints answer `409 review_required` when a policy
  applies. The SPA then sends the same change to `POST /proposals`. The UI's own check only chooses
  which button to show.

### 2. Change proposals
- **`change_proposal`** (tree-scoped, row-level security):
  - `proposer_id`;
  - `kind`: `change` or `challenge` (§6);
  - `status`: `draft → awaiting_review → accepted | rejected | withdrawn | stale`;
  - `rationale`, required on submit;
  - `decided_by`, `decided_at`, `decision_note`;
  - `supersedes_id`, set when a stale proposal is rebased (§5).
- **`change_proposal_item`** holds one atomic edit:
  - `target_type`: person, name, event (vital), relationship, assertion or person_link;
  - `target_id`, empty for a create;
  - `op`: create, update or delete;
  - `patch`, validated by **the same request schema as the direct endpoint**
    (`PersonUpdate`, `NameIn`, `RelationshipIn`…);
  - `base_revisions`, the revision of every record the item depends on (§3).

  A proposal holds at most 50 items.
- **`proposal_citation`** links sources (ADR-0009 citations) to the proposal. **`proposal_comment`**
  holds comments: plain text, at most 2,000 characters, editable by the author until the proposal
  is decided.
- **Applying.** Accepting a proposal runs the **same service functions** as a direct edit, in one
  transaction: all items apply or none do. The server checks again at that moment that:
  - the proposer could still make each change (they may have lost their role since);
  - the reviewer may review every target (§4).
- **Provenance.** The applied records keep their usual provenance. The revision rows (§3) name both
  the proposer and the reviewer.

### 3. Revisions and history
- **A revision counter.** `revision` (an integer, starting at 1) is added to `person`,
  `name_record`, `event`, `relationship` and `assertion`. It is incremented by every write, direct
  or applied, in the same transaction, using SQLAlchemy's version counter, so two concurrent writes
  cannot both win. A person's revision also increases when any of their own facts (names, vitals,
  heritage claims) changes. This gives creates and links something to bind to.
- **What an item binds to:**
  - an update or delete binds to the record's own revision;
  - a create under a person binds to that person's revision;
  - a link binds to the revisions of both people.
- **`record_revision`** (tree-scoped, row-level security) stores the history:
  - one row per write: record type and id, revision, `before` and `after` values (only the fields
    that changed), actor, time, and the proposal and reviewer if any.

  This is what the audit log deliberately is not, so it is protected like the facts themselves:
  - it is read through the same field-group redaction (ADR-0006). A viewer who cannot see a
    living person's full birth date sees "birth date changed", not the dates;
  - erasing a person (PRS §54) erases their revision rows too;
  - archive and GEDCOM exports leave it out.
- **History and revert.** A person's History tab lists their revisions. **Revert** creates a new
  change back to an earlier value. It is direct for those who write directly, and a proposal for
  everyone else. History is never rewritten.

### 4. Who reviews
- **A new permission, `change.review`**, held by owners and family admins everywhere, and by branch
  admins for people in their branch.
- **A new role, `REVIEWER`** (tree read plus `change.review`). It can be given alongside
  Contributor, so a trusted elder can review without administering the tree. This is an RBAC
  change, so the threat model gets a new entry before any code.
- **No self-approval.** A proposer can never decide their own proposal, even if they hold
  `change.review`.
- **The whole proposal.** A reviewer must be allowed to review every target of a proposal and to
  see every changed field. Otherwise they cannot decide it, and an owner or family admin must.
- **Stale approvals are impossible (§5).**

### 5. Bound to an exact revision
- **The reviewer sees today's state.** The proposal page shows each item as a diff against the
  **current** record, computed when the page is read and never cached, plus a warning when a base
  revision no longer matches.
- **Approval checks again.** It locks the targets (`SELECT … FOR UPDATE`) and compares every base
  revision. If any differs, nothing is applied and the proposal becomes `stale`. The reviewer is
  told which record changed.
- **Rebase.** A stale proposal can only be *rebased* by its proposer: a new proposal, linked by
  `supersedes_id`, against the current revisions, which needs a fresh review. An approval is never
  carried over.
- **Deleted targets.** A deleted or erased target makes its proposal stale, and its values leave
  the proposal (privacy erasure wins over review).

### 6. Review state and challenges
- **Review state is its own field.** `review_state` is added to `person`, `name_record`, `event`,
  `relationship` and `assertion`, with `review_state_by` and `review_state_at`:
  - `unreviewed` is the default;
  - `family_reviewed` is set when an accepted proposal touches the record, or when a reviewer
    confirms it directly;
  - `contested` is set by an upheld challenge.

  It is separate from `evidence_status` (no `FAMILY_CONFIRMED` value, plan principle 7) and from
  provenance. Any later change to the record sets it back to `unreviewed`.
- **Labels.** The UI shows its certainty words over these values:
  - document-supported = SOURCED or CORROBORATED;
  - family-reported = FAMILY_RECOLLECTION;
  - estimated = an imprecise date;
  - disputed = DISPUTED;
  - family-confirmed = `family_reviewed`;
  - challenged = `contested`.
- **Challenges.** Any member who can see a fact may **challenge** it, viewers included: elders often
  hold the knowledge.
  - A challenge is a proposal of kind `challenge`, with a required reason and optionally sources
    and a proposed correction. Opening one **does not** mark the fact: one member cannot stamp
    "challenged" across the tree. Reviewers see open challenges at once.
  - A reviewer either **upholds** the challenge or **dismisses** it with a note. Upholding sets
    `contested`, records `evidence_status = DISPUTED` if the reviewer chooses, and applies the
    correction if there is one, under the §5 checks.
  - At most 20 open challenges per member per tree.

### 7. In-app notifications
- **`user_notification`** (per user, tree-scoped, row-level security) covers:
  - a proposal awaiting your review;
  - your proposal accepted, rejected or stale;
  - a challenge to a fact you added;
  - a comment on a proposal you are part of.
- **Ids only.** A notification stores ids and a kind, **never names or values**. The text is built
  when it is read, with the reader's current permissions, so a notification never shows more than
  the reader may see now.
- **Nothing leaves the app.** A notification bell with an unread count; no email or WhatsApp for
  these in R3 (ADR-0016 channels stay for reminders).

### 8. Duplicates at entry (Phase J)
- **Where.** In Smart Add's details step and in the Add person / Add relative form, before the
  preview or save.
- **How.** The server scores the would-be person against existing people, reusing the PRS §24
  scorer. It compares names (across scripts, ADR-0007), birth year, the parents or spouse being
  linked, and the **LGD birth village** (ADR-0019) when both places are linked.
- **What the user sees.** At most 5 candidates, each with match reasons ("same parents", "birth year
  1932 vs 1931", "same village: Rampur"). The choices are:
  - **Use this person**, which links the existing person instead (an existing-person link, so
    §1 applies);
  - **This is someone else**, which proceeds.

  Nothing is merged or chosen automatically.
- **Privacy.** Only people the user can see are scored and shown. A hidden or provisional match is
  never revealed, not even as a count. Unique hits are therefore no oracle for hidden people.
- **Badge.** People with a likely duplicate (score ≥ 0.85) show a "possible duplicate" badge, visible
  to members who can see both people. It links to the existing compare-and-merge (ADR-0003 merge
  rules).

### 9. API
Under `/api/v1/trees/{tree_id}`, all authorised, typed and paginated by cursor:
- **Proposals:**
  - `POST /proposals` creates a draft or submits it; `GET /proposals` takes the filters
    `mine`, `to_review`, `status` and `target`;
  - `GET /proposals/{id}` returns the items, a live diff against current, the redacted values,
    comments and the stale warning;
  - `POST /proposals/{id}/submit`, `/withdraw`, `/approve`, `/reject` and `/rebase`;
  - `POST /proposals/{id}/comments`.
- **Challenges and review state:**
  - `POST /challenges`, the same shape as a proposal with `kind = challenge`;
  - `POST /proposals/{id}/uphold` and `/dismiss`;
  - `POST /review-state` sets `family_reviewed` directly (reviewers only).
- **History:** `GET /people/{id}/history` and `POST /revisions/{id}/revert`.
- **Duplicates:** `POST /duplicates/check`, which takes a draft person and anchor and returns
  candidates with reasons.
- **Notifications** (user-level): `GET /notifications`, `POST /notifications/read`.
- **Errors:** `409 review_required` and `409 proposal_stale` are structured errors.

### 10. Interface
- **Proposing.** Edits made under a policy open a *Propose change* sheet, with a rationale and
  optional sources. The person page shows "1 change awaiting review".
- **Reviewing.** A **Review** page (to review, mine, closed) shows side-by-side diffs with changed
  words highlighted, in both scripts. Approve and reject need a note on reject.
- **Facts.** They carry certainty labels (§6) and a "Challenge" action.
- **History** with Revert, a notification bell, and the duplicate panel in Smart Add.
- **Standards.** All of it works on a 390 px screen, follows the existing accessibility patterns
  (no colour-only states, polite announcements) and comes in English and Hindi.

## Consequences
- **One migration with a downgrade:**
  - new columns: `revision`, `review_state`, `review_state_by` and `review_state_at` on five tables;
    `review_policy` on `tree`;
  - new tables `change_proposal`, `change_proposal_item`, `proposal_citation`, `proposal_comment`,
    `record_revision` and `user_notification`, all with row-level security;
  - backfill: `revision = 1`, `review_state = unreviewed`, `review_policy = off`.
- **Every write path increments revisions and writes a `record_revision`:** person, name, vital,
  relationship and assertion services, Smart Add, GEDCOM import, merge and revert. Existing tests
  must keep passing with the policy `off`. A test asserts that every write endpoint for these five
  tables records a revision.
- **Threat model:** new entries for the reviewer role and self-approval, approving a stale proposal,
  diff and history redaction, challenge flooding, notification text leakage, and duplicate
  candidates leaking hidden people. The privacy model gets a section on revision history and erasure.
- **Storage:** about 1 KB per changed record per revision, so roughly 10 MB a year for an active
  10,000-person tree.

## Alternatives considered
- **Use the audit log for history.** Rejected: it deliberately holds no values. Putting values
  there would make the append-only, admin-readable log a second copy of every living person's data,
  with no redaction and no erasure.
- **Last write wins with a confirmation dialog.** Rejected: it doesn't let anyone else review, and
  two editors silently overwrite each other.
- **Review everything, always.** Rejected as a default: small families with one active editor
  would get only friction. A per-tree policy that starts `off` lets families choose.
- **A `FAMILY_CONFIRMED` evidence status.** Rejected (plan principle 7): family approval is not
  evidence, and mixing them would let a vote override a document.
- **Optimistic locking with no proposals (ETag/If-Match on every write).** Kept as a by-product
  (`revision`), but it doesn't give review or challenges.
- **Store a proposal as a full copy of the person.** Rejected: large diffs, hard to bind to exact
  records, and a copy of living data that outlives erasure.
- **Automatic duplicate merge at entry.** Rejected: merges are high-impact and reviewed (ADR-0003);
  at entry we only offer "use this person".
- **Email notifications for proposals.** Deferred: the channels exist (ADR-0016), but the value is
  low until families use review, and email bodies leak names outside the app.

## Stress test
1. *Can a reviewer approve something that changed after they looked?* No. Approval rechecks every
   base revision under a row lock; any change makes it stale and applies nothing (§5).
2. *Can someone approve their own change, or escape their branch by proposing?* No. Self-approval is
   refused, and proposing does not widen write rights: the server checks the proposer's rights when
   the proposal is created and again when it is applied (§2, §4).
3. *Does a proposal or history entry leak a living person's private data?* No. Diffs, history and
   notifications are redacted for each reader at read time, and erasure removes revision rows and
   proposal values (§3, §5, §7).
4. *Can one member mark the whole tree "challenged"?* No. A challenge marks nothing until a reviewer
   upholds it, and open challenges are capped per member (§6).
5. *What happens to families who don't want review?* Nothing changes: `review_policy` defaults to
   `off`, writes stay direct, and revisions and history simply start accumulating (§1, §3).
6. *Can duplicate detection reveal that a hidden person exists?* No. Only visible people are scored,
   hidden matches are never counted or hinted at, and nothing auto-merges (§8).
7. *What if the reviewer can't see part of the change?* They can't decide it. The proposal waits for
   someone who can see every changed field (§4).
8. *Can proposals be used to flood reviewers?* Proposals are capped at 50 items, with per-member caps
   on open challenges and rate limits on proposal creation. Proposers can't skip the rationale.
9. *What if a proposal touches a person who is then erased?* Erasure wins: the proposal goes stale
   and drops those values (§5).

## Open points for the reviewer
- **Default policy for new trees.** Proposal: `off` for every tree; the owner chooses during setup.
  Alternative: `structure` by default for trees with more than five members.
- **Branch admins as reviewers.** Proposal: yes, within their branch. Alternative: only owners,
  family admins and explicit Reviewers.
- **Viewers may challenge.** Proposal: yes, rate-limited and marking nothing until upheld.
  Alternative: contributors and above only.
- **History retention.** Proposal: keep revisions for as long as the record exists, erased with the
  person. Alternative: keep values for 2 years, field names only after that.
