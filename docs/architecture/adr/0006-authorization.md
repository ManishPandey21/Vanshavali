# ADR-0006: Authorisation and privacy evaluation

- Status: Accepted · Date: 2026-09-25

## Decision
**Deny by default**, centralised in `app/authz`:

1. **Resolve the context**: `AuthzContext(user, tree, membership?, is_public)`. A tree the caller
   is not a member of (and that is not public) → **404**.
2. **Action check**: `require(ctx, Permission.X, resource?)`, driven by the role matrix (below).
   Branch-scoped roles (`BRANCH_ADMIN`, or any membership with `branch_id`) only get write access to
   people in that branch's membership.
3. **Visibility check** (read): `can_view(ctx, obj)`, driven by the object's `privacy_level`:
   - `PRIVATE_SELF`: the claimed profile owner, plus the tree OWNER (who is responsible for the archive).
   - `PRIVATE_TREE_ADMINS`: OWNER and FAMILY_ADMIN (and the claimant).
   - `FAMILY_BRANCH`: admins, plus members whose branch scope or linked person belongs to one of
     the subject's branches.
   - `TREE_MEMBERS`: any member except RESEARCHER.
   - `INVITED_RESEARCHER`: any member, including RESEARCHER.
   - `PUBLIC_DECEASED_ONLY`: like TREE_MEMBERS, and also public if the tree has public mode on
     **and** the subject is deceased (never living, unknown or a minor).
   - `CUSTOM`: admins plus explicit `access_grant` rows.
4. **Field redaction** (`redact_person`): sensitive field groups (`birth_date_full`, `birth_time`,
   `birth_place_detail`, `contact`, `address`, `gender_identity`, `community`, `jati`, `astrology`,
   `notes`) are evaluated against a per-person override, else a default that depends on
   living/minor status. Living and unknown people, and minors, default `birth_date_full`,
   `birth_time`, `contact` and `address` to `PRIVATE_TREE_ADMINS`. Redacted date values are cut
   down to the year and flagged `redacted: true`. Public contexts always get the minimum.
5. **Documents**: `can_view` on the document, plus `DOCUMENT_DOWNLOAD` for bytes. VAULT documents
   also require OWNER, FAMILY_ADMIN or DOCUMENT_CUSTODIAN, or an explicit grant. Property documents
   also allow PROPERTY_CUSTODIAN.
6. **SYSTEM_ADMIN** has platform endpoints only (health, metrics) and **no implicit tree access**.

### Role → permission matrix (summary)
| Permission | Owner | FamAdmin | BranchAdmin | Contributor | Researcher | Viewer | DocCustodian | PropCustodian |
|---|---|---|---|---|---|---|---|---|
| tree.read | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| tree.manage (settings, public mode) | ✓ | ✓ | | | | | | |
| members.manage / invite | ✓ | ✓ | branch | | | | | |
| person.write / relationship.write | ✓ | ✓ | branch | ✓ | | | | |
| assertion.propose | ✓ | ✓ | ✓ | ✓ | ✓ | | | |
| source.write | ✓ | ✓ | ✓ | ✓ | ✓ | | | |
| document.upload | ✓ | ✓ | ✓ | ✓ | | | ✓ | ✓ |
| document.manage (vault, delete) | ✓ | ✓ | | | | | ✓ | |
| extraction.review | ✓ | ✓ | ✓ | ✓ | | | ✓ | ✓ |
| property.read / write | ✓ | ✓ | | read | | | | ✓ |
| gedcom.import | ✓ | ✓ | | | | | | |
| gedcom.export | ✓ | ✓ | | ✓ | | | | |
| audit.read | ✓ | ✓ | | | | | | |

Researchers' writes go in as `USER_ASSERTION` proposals that need admin acceptance. The full
proposal workflow is **DEFERRED** to post-MVP collaboration, so for now researchers can add sources
and assertions but can't edit people.

## Consequences
Every router uses a `tree_ctx` dependency and a `require()` call. A parametrised test checks that
every route under `/trees/{tree_id}` rejects non-members and returns 404 across trees.

## Amendment (8 Nov 2026): who may change or remove a membership
A membership may be changed or removed only by someone who could have granted **every role it
holds**. Before this amendment the rule held when roles were added but not when they were taken
away, so a family admin could delete another family admin's membership, and a branch admin could
demote or remove a peer branch admin or a custodian in its branch.

| Caller | May give or take away | May change or remove the membership of |
|---|---|---|
| Owner | every role | anyone; the last owner can never be removed or demoted |
| Family admin | every role except owner and family admin | members holding none of those two roles |
| Branch admin | contributor, researcher, viewer | members of its own branch who hold only those roles |
| Anyone else | nothing | nobody |

Nobody changes their own roles, except an owner. Leaving the tree is not an escalation.

Every role change is audited:
- `member.updated` records the previous and the new roles, and whether an owner or family-admin
  role changed;
- `member.removed` records the roles that were removed.

The API tells the UI what the caller may do (`my_grantable_roles` on the tree, `can_manage` on each
membership) so it offers only those controls. The server re-checks every change.

Promoting a member to family admin stays the owner's decision. A workflow in which a family admin
*nominates* a member and the owner approves is a separate change to this ADR (tracked as an issue).

## Amendment (9 Nov 2026, **Accepted**): Family Admin nominations, approved by an Owner
Status: **Accepted** on 9 Nov 2026 by the owner, with the decisions recorded at the end. Not built
yet. Tracked in issue #45; threat-model entry T56.

### Context
- Owners want Family Admins to be able to **put a member forward** for Family Admin. The decision
  stays with an **Owner**.
- Today only an Owner can grant or remove Owner and Family Admin roles (amendment of 8 Nov 2026).
  There is no nomination workflow.
- Becoming a Family Admin is a large change:
  - the member gains every permission except deleting the tree;
  - they can see `PRIVATE_TREE_ADMINS` data (full birth dates, contact details, addresses, jati and
    astrology of living people). `PRIVATE_SELF` stays Owner-only, and ADR-0027's private audiences
    ("Only me", "Selected members") stay closed to every role;
  - they can read the audit log.

  So the workflow must never grant the role by itself, and the person being promoted must agree.

### Decision
1. **Who may nominate.** Only a **Family Admin** may nominate. An Owner doesn't need to: they grant
   the role directly, as today. Branch Admins, Contributors, Reviewers, Researchers, Viewers and
   custodians cannot nominate.
2. **Who may be nominated.** An existing member of the tree who:
   - is not an Owner or Family Admin already;
   - is not the nominator (**no self-nomination**);
   - has no other open nomination.
3. **What a nomination holds:**
   - the nominator, the nominee's membership and a reason (at most 500 characters);
   - the time it was made, and an **expiry 14 days later**;
   - a status: `open` → `approved` | `declined_by_owner` | `declined_by_nominee` | `withdrawn` |
     `expired` | `lapsed`.

   It is tree-scoped and under row-level security, like every tree table.
4. **Two consents, in either order. Neither alone changes anything.**
   - **The nominee accepts or declines.** Declining ends the nomination.
   - **An Owner approves or declines.** Only an Owner's approval can grant the role, and only once
     the nominee has accepted. The Owner who approves is recorded.
   - On approval, the role change goes through the existing `update_member` path, **as that
     Owner**, with every existing rule and the same audit (`member.updated`, `admin_change: true`).
5. **Branch scope.** Family Admin is a whole-tree role. If the nominee's membership is
   branch-scoped, the Owner's approval screen says plainly that approval removes the branch
   scope. The approval request must confirm it explicitly (`clear_branch: true`); otherwise it is
   refused.
6. **Lapsing.** An open nomination lapses automatically if:
   - the nominator loses the Family Admin role or leaves the tree;
   - the nominee leaves the tree;
   - the nominee becomes an Owner or Family Admin by another route.

   A nominator may withdraw at any time before approval.
7. **Who sees nominations.**
   - Owners and Family Admins see every open nomination, including the reason.
   - The nominee sees their own: who nominated them and the reason.
   - Nobody else sees any.
8. **Notifications.** In-app only, through the existing notification inbox (ADR-0021 §7), storing a
   kind and ids:
   - Owners and the nominee are told of a new nomination;
   - the nominator is told of every outcome.

   No email or SMS in v1.
9. **Audit.** Each step is its own audit event: `admin_nomination.created`, `.accepted_by_nominee`,
   `.declined_by_nominee`, `.approved`, `.declined_by_owner`, `.withdrawn`, `.expired`, `.lapsed`.
   Events record the actor, the nominee's membership and the outcome, but not the reason text.
10. **Limits.** At most 5 open nominations per tree. Every endpoint is rate-limited per user.
11. **API** (all under `/api/v1/trees/{t}`, typed and authorised):
    - `POST /admin-nominations` (Family Admin) and `GET /admin-nominations` (Owners, Family Admins,
      or the nominee for their own);
    - `POST /admin-nominations/{id}/accept`, `…/decline` (nominee);
    - `POST /admin-nominations/{id}/approve`, `…/reject` (Owner);
    - `POST /admin-nominations/{id}/withdraw` (nominator).

### Threats and tests to write before code
Threat-model entry **T56** covers:
- a nomination used to escalate (self-nomination, or a non-Family-Admin nominating);
- a role granted without the nominee's consent or without an Owner;
- approval of a stale nomination after the nominator was demoted;
- IDOR across trees;
- the reason text or the nominee's identity reaching other members.

Tests required:
- self-nomination refused;
- Viewer, Contributor, Reviewer and Branch Admin cannot nominate;
- an Owner cannot approve before the nominee accepts, and nobody but an Owner can approve;
- the role is unchanged until approval;
- branch scope is cleared only with explicit confirmation;
- lapsing on every trigger in (6), and expiry after 14 days;
- cross-tree IDOR on every endpoint;
- visibility of the reason;
- the audit trail for each step;
- the last-owner and no-self-escalation rules still hold.

Plus a Vitest for the nomination screens and a Playwright flow (nominate → accept → approve).

### Alternatives considered
- **A Family Admin promotes directly.** Rejected by the owner: promotion stays an Owner decision.
- **A quorum of two Family Admins instead of an Owner.** Rejected: it would move a decision the
  owner kept for Owners.
- **No consent from the nominee.** Rejected: the role widens what the person sees of living
  relatives' private data, and the duty should be accepted, not assigned.
- **A message to the Owner outside the app.** Rejected: there would be no record, no expiry and no
  audit trail.

### Stress test
1. *A Family Admin nominates themselves, or nominates through a second account.* Self-nomination is
   refused. A second account is a separate member, so it still needs its own acceptance, an
   Owner's approval and the audit trail.
2. *The nominator is demoted while a nomination is open.* The nomination lapses, and the Owner
   can't approve it.
3. *An Owner approves before the nominee has seen it.* Refused: the nominee's acceptance comes
   first.
4. *Two Owners act at once.* The first decision wins, and the second gets a conflict.
5. *A branch-scoped cousin is nominated.* The Owner sees that approval removes the branch scope,
   and must confirm it.
6. *The nominee leaves the tree.* The nomination lapses.

### Decisions on the open points (owner, 9 Nov 2026)
1. **Expiry: 14 days.** The limit of 5 open nominations per tree is accepted as proposed.
2. **Branch Admins cannot nominate.** Only a Family Admin nominates (§1 of this amendment).
3. **The nominee sees the reason**, together with who nominated them (§7).
