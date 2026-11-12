# ADR-0027: Record visibility and selective sharing for family media and records

- Status: **Accepted** · Date: 2026-11-09 (accepted as proposed by the owner; the open points
  are resolved as below) · Implementation: increments 1 (documents), 2 (traditions), 3 (event photo albums) and 4 (photo collections), and later increments — see the implementation notes
- Amends: ADR-0006 (privacy levels, grants, admin visibility), ADR-0004 (view vs download),
  ADR-0015 (album × photo, tags). Cross-references **ADR-0023** (oral history, proposed, PR #42):
  that ADR keeps its consent rules; this ADR supplies the sharing mechanics it relies on.
- Relates to: ADR-0011 (invites), ADR-0017 (exports), ADR-0021 (review), ADR-0026 (traditions),
  Q13 (lawful basis for living relatives).

## Context
Families want to decide exactly who sees a photograph, a certificate, a recording or a story. The
app already has most of the parts — `privacy_level` on documents, events and traditions,
`access_grant` with `view` and `download`, signed download URLs re-authorised at serve time, and
album filtering — but an audit (8 Nov 2026, probes run against the test stack) found that they do
not add up to "only the people I chose":

| # | Finding (current `main`) | Evidence |
|---|---|---|
| A1 | **`CUSTOM` always includes `OWNER` and `FAMILY_ADMIN`.** A family admin with no grant can read and download a `CUSTOM` document. | `authz/privacy.py::level_allows`; probe: admin → 200, download URL → 200 |
| A2 | **`PRIVATE_SELF` on a document means "uploader + tree owner"** (owner as archive custodian, ADR-0006 §3). There is no "only me". | probe: tree owner → 200 on a contributor's `PRIVATE_SELF` photo |
| A3 | **Grants are keyed by `user_id`, not by membership.** Removing a member leaves their grants; if the same person is invited again, every old grant is live again. | `access_grant.user_id`; probe: 1 grant left after removal, old `CUSTOM` doc → 200 after re-invite |
| A4 | **`FAMILY_BRANCH` on a document cannot work:** documents carry no branch, so `level_allows(subject=None)` denies every non-admin. | probe: branch member → 404 |
| A5 | **Only document managers can change a document's privacy.** An uploader cannot even make their own photo *more* private after upload. | `documents/service.py` update; probe: 403 |
| A6 | **View implies original download** for non-vault documents. `view`/`download` grants only differ for the vault class. ADR-0006 §5 names a `DOCUMENT_DOWNLOAD` permission that does not exist. | `documents/access.py::can_access_content` |
| A7 | **`GET /trees/{id}/grants` lists every grant in the tree** to any privacy manager, which reveals that a private record exists and who may see it. | `trees/router.py::list_grants` |
| A8 | **Tagging a person never tightens a record.** ADR-0015 inherits the principal's level only when a photo is *added to an event*; a `document_link` to a protected living person leaves the document as open as it was. | `documents/service.py::_add_link` |
| A9 | **Traditions evaluate privacy themselves** (`traditions/service.py::may_read`): there `PRIVATE_SELF` means author-only and `CUSTOM` means admins-only (no grant resource exists for traditions). Same words, different meaning. | code |
| A10 | **A record's owner has no way to share it.** The only grant UI (`GrantsPanel`) is for privacy managers and only on `CUSTOM` records. *(Corrected 9 Nov 2026: the first audit said there was no grant UI at all.)* | `components/privacy/GrantsPanel.tsx` |

What already holds and is kept: deny by default and 404 for anything not visible; tree-scoped
lookups, composite FKs and row-level security (T1); `can_view_document` is the single predicate used
by document reads, search, event albums, story/visualization photos and the archive ZIP, so fixing
it fixes all of them; signed URLs bound to (document, tree, user, variant), ≤300 s, re-authorised on
every fetch (T5); a system admin has no tree access (T12); event albums already require *event
visible ∧ photo visible* (ADR-0015).

## Decision

### 1. Five audiences, one field
A **shareable record** is a document (photos, videos, certificates, historical and property
documents), an oral-history story (ADR-0023), a tradition entry (ADR-0026) and, later, a photo
collection (§6). Its `privacy_level` takes one of these audiences:

| UI choice | Stored `privacy_level` | Who can see it |
|---|---|---|
| **Only me** | `ONLY_ME` (new) | The content owner(s) (§2). Nobody else, whatever their role. |
| **Selected members** | `SELECTED_MEMBERS` (new) | The content owner(s) and memberships holding an unexpired grant on the record. |
| **Selected branch** | `FAMILY_BRANCH` + `audience_branch_id` (new column) | The content owner(s), members of that branch (membership scope or linked person, as today), and grantees. |
| **All family members** | `TREE_MEMBERS` | Every member except researcher-only memberships, as today. |
| **Public** | `PUBLIC_DECEASED_ONLY` | Only where already supported (deceased-only public trees). **Never** for oral history, traditions, vault documents or anything tagged with a protected person. |

- **The two private audiences have no role-based visibility.** `OWNER`, `FAMILY_ADMIN`,
  `BRANCH_ADMIN`, `DOCUMENT_CUSTODIAN`, `PROPERTY_CUSTODIAN`, `REVIEWER` and the system admin see
  nothing of an `ONLY_ME` or `SELECTED_MEMBERS` record — not its bytes, title, thumbnail, count,
  grant list or audit target — unless they are its owner or a grantee. Only §8's exceptions apply.
- **The shared audiences keep ADR-0006's meaning**, so `FAMILY_BRANCH` and `TREE_MEMBERS` still
  include admins. "Who has access" (§9) lists them by name, so nobody is surprised.
- **`CUSTOM` and `PRIVATE_SELF` are not redefined.** They keep their current meaning for people,
  properties and existing records, so no stored record silently becomes more open or more closed.
  New UI never writes them on a shareable record; existing records show a "legacy" badge that
  names the extra viewers (e.g. "Selected members and family admins") and offers a one-click
  conversion to the new audience, which only the content owner can make (§10).
- People and field groups reject `ONLY_ME` and `SELECTED_MEMBERS` (422): person privacy remains
  ADR-0006's model.
- Evaluation stays in `app/authz`: `level_allows` gains the two levels and an `owner` argument, and
  `traditions.may_read` is folded into it (A9). There is no second engine.

### 2. Content owner
- Each shareable record gets `owner_membership_id` (FK to `tree_membership`, `ON DELETE SET NULL`),
  backfilled from `created_by` where that user is still a member.
- An oral-history story has two holders, the **narrator** (if they have an account) and the
  **interviewer**. The narrator's consent is the ceiling (§5); the interviewer cannot widen it.
- The owner may transfer ownership to another member, who must accept; the transfer is audited.
- **Orphaned private records** (owner removed or left, no transfer): they stay visible only to
  existing grantees and are listed to nobody else. They are kept under their retention policy and
  removed by the system job when it ends. Admins cannot claim them.

### 3. Grants belong to memberships
- `access_grant` gains `membership_id` (FK to `tree_membership`, **`ON DELETE CASCADE`**), backfilled
  from `(tree_id, user_id)`; rows with no current membership are deleted. Lookups use the
  membership. `user_id` stays for one release, then is dropped.
- So **removing a member deletes their grants at once**, and a later invite creates a new membership
  with no grants (fixes A3). The cached grant set is per request, so the next request fails.
- Grants exist on `document`, `story`, `tradition` and (later) `collection`; new
  `GrantResource` values. A grant names `view` or `download` (download implies view, as today).
- **Only the content owner** creates or revokes grants on an `ONLY_ME`/`SELECTED_MEMBERS` record.
  `privacy.manage` keeps its rights over people, properties and the shared audiences.
- No cross-tree grants: the grantee membership must belong to the record's tree (composite FK).
- New members get nothing automatically, except what "All family members" means by definition;
  the selector says so.
- `GET /trees/{id}/grants` returns only grants on resources the caller may manage (fixes A7). A
  record's own `GET …/sharing` returns its grants to its owner only.

**Implemented (9 Nov 2026):** `membership_id` with the composite FK and cascade, backfill and
orphan deletion (§12.2, migration `9c4f2a7d1e83`); lookups by membership; `GET /grants` (and grant
creation and revocation) limited to records the caller may see — `privacy.manage` plus visibility
until §2 defines a content owner. **Waits for §1/§2:** owner-only granting on `ONLY_ME` /
`SELECTED_MEMBERS` records, `GET …/sharing`, and the new `GrantResource` values (§12.4).
**Next release:** drop `access_grant.user_id`.

### 4. View, preview, play and download
- **View** = metadata, thumbnail, preview, in-app playback/streaming, OCR text and confirmed
  extracted facts.
- **Download** = the original bytes as an attachment, and inclusion in ZIP, PDF and video exports.
- A record has `allow_download` (new boolean). When true, everyone who can view may download; when
  false, only owners and holders of a `download` grant. Existing rows: `true` (unchanged behaviour,
  A6). New uploads: `false` for vault-class documents, oral history and anything tagged with a
  protected person; `true` otherwise. Vault documents still also need the vault rule of ADR-0004.
- Streaming uses the existing signed-URL route with an `inline` variant bound to the user, so a
  revoked viewer's next segment request fails. A capture by an authorised viewer is a residual risk.
- ADR-0006 §5's "`DOCUMENT_DOWNLOAD`" is replaced by this rule.

### 5. Ceilings: consent and the privacy of tagged people
The owner chooses, but cannot go beyond the record's **ceiling**: the strictest of
1. the narrator's consent (stories, ADR-0023 §4): without scope 4 the ceiling is `ONLY_ME`;
2. every tagged **protected** person's level, mapped as: `PRIVATE_SELF`/`PRIVATE_TREE_ADMINS`/
   `CUSTOM` → `SELECTED_MEMBERS`; `FAMILY_BRANCH` → that person's branch; `TREE_MEMBERS` → all
   family. Deceased people do not cap the record;
3. for photos in an event album, the event's level (ADR-0015, unchanged).

A choice wider than the ceiling fails with `422 privacy_too_open`. Adding a tag or withdrawing
consent that lowers the ceiling **narrows the record at once** (never widens it) and tells the owner.
Tagging gives the tagged person no access, but they can ask for the tag to be removed (ADR-0023 §6).
The server recomputes the ceiling on every change; the UI only greys options out.

### 6. Albums and their photos
- Effective visibility of an item in an album = **album visible ∧ item visible**. Album listings,
  item counts, covers, thumbnails, stories, visualizations, search and exports use only items the
  viewer may see. A hidden cover is replaced by the first visible item; an album with no visible
  items still shows its own metadata, with no count of hidden items.
- Today's albums are event albums, whose album-level privacy is the event's. A standalone
  **photo collection** (an album not tied to an event) is a later increment using the same rule
  and the same selector; it is not in the first implementation PR.
- Sharing an album never shares its items: a member chosen for the album sees only items that
  already admit them, and the selector warns the owner which items they will not see.

### 7. Revocation and expiry
- Changing the audience, revoking a grant, removing a member, withdrawing consent or deleting a
  record takes effect on the next request: every route re-evaluates, and signed URLs (≤300 s,
  5 min for audio per ADR-0023) are re-authorised when fetched (T5).
- Already-downloaded copies and completed exports cannot be recalled; the warning before a widening
  change says so.

### 8. Narrow custodial exceptions (audited)
No role reads a private record. The only exceptions:
1. **System jobs** (malware rescan, derivative generation, withdrawal, erasure, retention, quota)
   run as the system, return no content to any user, and are audited as `system`.
2. **Takedown.** A family admin may **suspend** a record reported for abuse or a legal request, by
   its report reference, without seeing it. Suspension hides it from everyone but its owners until
   the owner appeals or the legal review (ADR-0023 §13) decides. The admin never sees content.
3. **Death or incapacity of the owner:** ADR-0023's Legacy Nominee, never admins or heirs by default.
Each exception is a separate permission, logged with actor, reason code and record id. Any other
exception requires amending this ADR.

### 9. The Visibility & Sharing component
One React component used on upload and on every record page:
- a radio group with the five audiences (unavailable ones shown disabled with the reason, e.g.
  "Narrator has not agreed to share" or "Tagged: Kamla Devi (private)");
- for **Selected members**, a searchable checklist of current members by display name and linked
  person (Indic and Latin search); for **Selected branch**, a branch picker;
- separate **Can view** and **Can download** toggles per chosen member, and the record-level
  "allow download" switch;
- "**Who will have access**": the exact list, including admins for shared audiences, computed by
  the server (`GET …/sharing/preview`), never by the client;
- a confirmation that lists the newly added viewers before any change that widens access;
- revoke and change later from the same component; a privacy badge on every document, photo,
  album, recording and tradition card.
Defaults: **Only me** for new vault documents, oral history and records tagged with a protected
person; the tree default otherwise (as today), never wider than the ceiling.

### 10. Who may change a setting
| Change | Content owner | Grantee | Admin / custodian |
|---|---|---|---|
| Narrow (any audience) | yes | no | yes, for records they can see (shared audiences only) |
| Widen | yes, up to the ceiling | no | no |
| Grants on a private record | yes | no | no |
| Grants on a shared record | yes | no | with `privacy.manage` |
Fixes A5. Promoting a member to any role grants no access to private records (§1).

### 11. Audit without content
New audit actions: `record.visibility_changed` (old and new audience, counts of added and removed
viewers), `grant.created` (exists), `grant.revoked`, `grant.cascade_removed`, `record.suspended`,
`record.ownership_transferred`, `document.downloaded` (exists), `media.played`. Details never hold
titles, captions, transcripts, file names or tokens. The audit API shows a private record's events
only to its owners; other readers see an opaque "private record" entry with no id.

### 12. Migrations (Alembic, each with a downgrade)
1. Add the enum values `ONLY_ME` and `SELECTED_MEMBERS` (downgrade: map them to `PRIVATE_SELF` and
   `CUSTOM`, the nearest existing levels, then drop the values).
2. `access_grant.membership_id` + backfill + delete orphaned grants (downgrade: drop the column;
   deleted orphans are not restored — they were already unreachable).
3. `owner_membership_id`, `audience_branch_id`, `allow_download` on documents (and stories and
   tradition entries when they exist), with backfill.
4. New `GrantResource` values.

### 13. Tests required by the implementation PR
Backend (each also as an admin, branch admin, custodian, viewer, researcher and a stranger from
another tree): an excluded member gets 404 for metadata, thumbnail, preview, stream, download URL
and signed file; no hit and no count in search, life-event listings, album counts or covers; nothing
in GEDCOM, ZIP, PDF or video exports; no row in `GET /grants` or the audit API. Plus: grants removed
with the membership and not revived on re-invite; a stale signed URL after revoke, removal, consent
withdrawal and expiry; cross-tree grant and IDOR attempts; promotion to `FAMILY_ADMIN` reveals
nothing; ceiling enforcement on tagging and consent; album with a restricted photo. Frontend:
component tests of the selector (search, multi-select, warnings, en/hi). Playwright: upload as Only
me → selected member sees it, another member and a family admin get "not found"; album shared with
the family shows only permitted photos.

## Consequences
- One meaning per word: the private audiences are truly private, and admins are told who they
  cannot see rather than silently seeing everything.
- Admins lose the ability to audit private content; abuse handling relies on the takedown path.
  This is a deliberate trade, as in ADR-0023 §3.
- Two legacy levels (`CUSTOM`, `PRIVATE_SELF` on records) remain until owners convert them.
- `level_allows` gains an argument; every caller passing records must supply the owner.

## Alternatives considered
- **Redefine `CUSTOM` to exclude admins.** Rejected: it would silently remove access the family
  relies on for people and existing documents, which the brief forbids.
- **A separate ACL table and evaluator for media.** Rejected: a parallel engine; `access_grant`
  already has the right shape once it is tied to memberships.
- **Grants against person records** (share with "Ramesh" the ancestor). Rejected: a person record
  is not an account; only a verified membership can hold access.
- **Admin break-glass read.** Rejected for v1; the takedown path covers abuse without reading.

## Stress test
1. *A family admin is promoted to owner.* Nothing private becomes visible: roles never enter the
   private branch of `level_allows`.
2. *A cousin is removed after a quarrel, then re-invited a year later.* The old grants were deleted
   with the old membership; the new one sees only shared audiences.
3. *A wedding album is shared with all family; one photo shows a minor and is Only me.* Listings,
   counts, cover and exports exclude that photo for everyone but its owner.
4. *An uploader tags a living aunt whose profile is private.* The photo narrows to Selected members
   at once; the aunt does not gain access but can ask for the tag to go.
5. *An interviewer tries to share a narrator's private story with the branch.* Without consent
   scope 4 the ceiling is Only me: 422.
6. *An admin guesses a private document's id.* 404 on every route, no audit row visible to them.
7. *A grantee holds a signed URL when access is revoked.* The next fetch is re-authorised: 403.

## Open points (resolved on acceptance, 9 Nov 2026: as proposed)
1. Should **Selected branch** include family admins (this ADR: yes, as ADR-0006's `FAMILY_BRANCH`)
   or be strictly branch members?
2. Legacy `CUSTOM` and `PRIVATE_SELF` records: keep until owners convert (this ADR), or convert all
   of them at migration with a notice?
3. The takedown path (§8.2): confirm it needs no admin read access, pending the legal review.
4. Is **Public** needed for any media in v1, or should records stay members-only until Q13 is
   answered?

**Resolutions.**
1. Yes: **Selected branch** keeps ADR-0006's `FAMILY_BRANCH` meaning and includes family admins; the
   "who has access" list names them.
2. Legacy `CUSTOM` and `PRIVATE_SELF` records are **kept until their owners convert them**; nothing
   is converted at migration.
3. The takedown path gives **no read access**; the legal review (ADR-0023 §13) may tighten it but
   not widen it.
4. **No public records in v1.** Public pages serve no documents today, so under §1 ("only where
   already supported") the Public audience is not offered for any record until Q13 is answered and
   this ADR is amended.

## Takedown in detail: reports, suspension and appeals (§8.2; owner's decisions of 9 Nov 2026)
These detail §8.2 as the owner decided them on 9 Nov 2026. They do not change this ADR's status or
any accepted decision: no role gains read access, and the legal review may tighten them but not
widen them.

1. **Reports.** A member who can see a record may report it (reason code and an optional note in
   their own words, at most 500 characters). Each report gets a reference such as `R-7F3K2Q`. The
   record's owner cannot report their own record. A member who cannot see a record cannot report it
   (404). The reporter's identity is never shown to the record's owner, in any notice or view; the
   admins handling reports see the reason and the note, not who reported (the audit log keeps the
   actor for accountability, readable only by those with `audit.read`).
2. **Suspension.** A member with the new `record.takedown` permission (owners and family admins)
   may suspend the record a report is about, or dismiss the report as mistaken, by its reference,
   without seeing the record. Nobody may act on a report about their own record. Suspension hides
   the record from everyone but its owner, on every route (detail, lists, albums, collections,
   search, export, grants, signed links), and stops it being widened: while suspended, its audience
   can only narrow and grants can only be revoked. It changes nothing else: no level, grant or
   link is saved, moved or removed.
3. **Appeal.** The owner may appeal once, with a note. The suspension stays in effect while the
   appeal is reviewed. The review is due **14 days** after the appeal.
4. **Who decides.** A member with `record.takedown` who is not the record's owner decides: uphold
   (the suspension stays; the appeal is closed) or lift. Where another such member exists, the
   admin who suspended the record may not decide its appeal (403 `different_reviewer_required`).
   **Fallback for a tree with one such admin:** that admin may decide, but must confirm it
   explicitly (`confirm_sole_reviewer`); the decision is marked as a sole-reviewer decision in the
   record and the audit. Lifting without an appeal (a mistaken suspension) follows the same rule.
5. **Lifting re-evaluates; it restores nothing.** On lifting, the record is shown again under its
   *current* audience, grants, memberships and privacy ceilings, re-checked at that moment (a
   ceiling that narrowed during the suspension narrows the record at once). Nothing saved before
   the suspension is restored: grants revoked and members who left during the suspension stay
   gone, and signed links issued before it stay invalid once expired (links are short-lived and
   re-checked at use).
6. **Notices and records.** The owner is told of the suspension, and of the decision (upheld or
   lifted, with its reason code and the decider's note). The reporter is told only that their
   report was reviewed. The suspension keeps who suspended and who decided, when, the reason code,
   whether the decider was the sole reviewer, and the notes; the audit holds ids, codes and flags
   only, never titles, notes or content.
7. **Deadline and escalation.** An appeal not decided by its due date is escalated once: every
   member who may decide it, and the tree's owners, are told it is overdue. Neither the deadline
   nor the escalation restores access; only a decision does.
8. **Still open (separate decision):** routing legal requests (for example a court or police
   request about a record nobody in the tree has reported) and the legal review's role in
   deciding appeals (ADR-0023 §13). Until then, only member reports start a takedown.
9. **An ownership offer (§2) that exists when a record is suspended (the owner's decision of 9 Nov
   2026, option 1 of two considered).** The suspension **cancels any pending offer in the same
   transaction**. While the record is suspended **no new offer and no acceptance succeeds**. After a
   lift the old offer does not return: **the owner must make a fresh offer**. Suspension and
   acceptance of the same record are serialised: if the acceptance completes first, the suspension
   and its notice apply to the new owner; if the suspension completes first, the acceptance fails
   and ownership does not move. The member it was offered to is not told and cannot tell a
   suspension from any other missing offer (the same 404); the cancellation is audited as the
   system, with no actor and no reason. (Option 2, pausing the offer during the suspension, was not
   chosen.)

## Suggested cross-references for ADR-0023 (PR #42), not made here
- §3 "Private" maps to `ONLY_ME` with two holders; "Shared in the tree" maps to the Selected
  members / branch / all family audiences, all needing scope 4.
- §6 "Hiding a passage" restricts the recording to "narrator, interviewer **and tree admins**",
  which contradicts §3 (admins see no private story). Suggest "narrator, interviewer and the
  assigned reviewer".

## Implementation notes (9 Nov 2026, increment 1: documents)
Covers every route to a document, which also covers photos, videos, certificates, property and
historical records, GEDCOM-imported photos and event-album photos.

- **Model.** `RecordPrivacyLevel` (every `PrivacyLevel` value plus `ONLY_ME` and `SELECTED_MEMBERS`)
  on `document.privacy_level` only; other tables keep `PrivacyLevel`'s CHECK constraint, so people,
  events and properties cannot hold the new values. New columns `document.owner_membership_id`,
  `audience_branch_id`, `allow_download`. Migration `3f6a8c1d2e94` (after `9c4f2a7d1e83`, which
  bound grants to memberships, ManishPandey21/Vanshavali#49) backfills owners from `created_by`; its
  downgrade maps the new levels to `PRIVATE_SELF` and `CUSTOM`.
- **One evaluator.** `authz.privacy.record_allows` sits beside `level_allows` and delegates to it
  for every shared or legacy level; `level_allows` refuses the record-only levels outright (fail
  closed). Grant management uses #49's `trees.service.manageable_grant_resources`, extended so a document's
  owner manages its grants and grants on a private record are the owner's alone. The uploader
  fallback (`created_by`) is replaced by the owner membership, so a re-invited uploader does not get
  their old records back.
- **View / content / download.** `documents.access`: view → content (thumbnail, preview, OCR text,
  a new `stream` variant for audio and video, served inline) → download (original, archive ZIP,
  photos inside video exports). For vault documents at shared levels the custodian rule still grants
  download; it never applies to the private audiences.
- **Sharing API.** `GET|PUT /documents/{id}/sharing` and `POST …/sharing/preview`. "Who has access"
  is computed by evaluating the real rules for every membership against the proposed settings.
  `PATCH privacy_level` follows the same rules. `409 confirm_wider` before anyone new can see or
  download; `403 owner_only_widening` for managers; `422 privacy_too_open` above the ceiling.
- **Ceilings.** Linking a person (`_add_link`, uploads with a link) and `set_privacy`/erasure of a
  person narrow the linked records. Citations: a source about a private record is visible exactly to
  the record's audience (`evidence.can_view_source`), and its stored level is the nearest older one.
- **Albums, exports, audit.** Album listings, counts and covers use visible photos only, and a
  hidden cover falls back to the first visible photo. The archive includes bytes only where the
  exporter may download. The audit API turns entries about records the reader cannot see into an
  opaque `private_record` entry.
- **UI.** `components/privacy/VisibilitySharing.tsx` (the reusable control: four audiences, a
  searchable member checklist with separate *Can view* / *Can download*, branch picker, download
  switch, the server-computed "who has access" list, ceiling reasons) used in the upload dialog and
  in `DocumentSharingPanel` on every document page (with a confirmation before widening).
  `RecordPrivacyBadge` on document cards, document pages and album photos. The document metadata
  form no longer edits privacy.
- **Tests.** `tests/test_record_sharing.py` (21 cases), component tests
  `VisibilitySharing.test.tsx`, Playwright `record-sharing.spec.ts`; threat model T54/T55.
- **Follow-up: grantees only read (§10).** Items promised by the closed #52 and not carried by #50.
  A member a private document is shared with may read it (and download when allowed), but may not
  rename it, link or tag it, add it to an album or property event, reprocess it, review its
  extraction proposals, delete or restore it, whatever their role: `documents.access.
  require_owner_if_private` returns `403 not_content_owner`, and `DocumentOut.can_change` lets the
  UI hide those controls. Shared audiences keep the role rules. A property's
  `hidden_document_count` no longer counts other members' private records (§1: no count).

**Not in increment 1:** oral history (waits for ADR-0023), traditions (still `may_read`, finding
A9), standalone photo collections, takedown by suspension, ownership transfer, notifying the owner
of an automatic narrowing, and narrowing when a profile is hidden during a claim review. These are
listed in the threat model's residual risks.

## Implementation notes (9 Nov 2026, increment 2: family traditions)
- **Shared core.** The sharing rules moved to `app/modules/sharing/core.py` behind a small
  `RecordAdapter` (how to evaluate a proposed setting, how to store it, which people are linked,
  whether there is a download right). Documents (`documents/sharing.py`) and traditions
  (`traditions/sharing.py`) are adapters; the API, the "who has access" computation, ceilings,
  confirmation and grant replacement are one code path.
- **Traditions are records.** `tradition_entry.privacy_level` takes `RecordPrivacyLevel`; new
  `owner_membership_id` (backfilled from `created_by`). `traditions.may_read` is now
  `record_allows` (finding A9 closed): the private audiences admit no role. Traditions always used
  `PRIVATE_SELF` for *the author only*, so migration `8d2e6b4f1a37` moves those rows to `ONLY_ME` and
  the API maps a submitted `PRIVATE_SELF` to `ONLY_ME` (see the exception below). "Selected
  branch" is the entry's existing `branch_id`; moving a Selected-branch entry to another branch is an
  audience change and follows §10. Entries are text: no separate download right. Never public.
- **Exception to open point 2 (accepted for traditions only).** Resolution 2 keeps legacy
  `PRIVATE_SELF` records until their owners convert them. Traditions are converted at migration
  instead, because their `PRIVATE_SELF` never had the tree-owner custodian meaning that it has on
  documents: it meant *the author only*. Documents and every other record keep resolution 2. What
  the conversion changes, exactly (tested in `tests/test_traditions_sharing.py`):
  - *At migration time nobody gains or loses access*: an entry's readers are its author, if still a
    member, before and after.
  - *Re-invited authors.* The old rule matched the author's user id, so an author removed and invited
    again read their old private entries again. Now the owner is a membership: a re-invited author
    does not get them back (ADR-0027 §3, stress test 2). This is permanent.
  - *Orphans.* An entry whose author had already left has no owner: nobody can read, share, convert
    or claim it, not even that author if re-invited. It stays under its retention policy (§2).
  - *Unchanged:* `CUSTOM` entries stay `CUSTOM` (admins and grantees); no grants are created or
    deleted on upgrade; grants on people, documents and properties are untouched.
  - *Downgrade (not reversible in effect):* tradition grants are deleted, so selected members lose
    access; `SELECTED_MEMBERS` becomes `CUSTOM`, so tree owners and family admins *gain* read access
    to those entries; `ONLY_ME` becomes `PRIVATE_SELF`, so a re-invited author reads their old entries
    again; owners (and any transfer of ownership) are dropped. Upgrading again re-runs the owner
    backfill from `created_by`, so a re-invited former author then owns their old entries. A
    downgrade therefore needs the same approval as a privacy change.
- **Grants.** `GrantResource.TRADITION`; `manageable_grant_resources` treats entries like documents
  (owner, or a privacy manager for a shared entry); `ONLY_ME` cannot be granted directly (409).
- **Ceilings.** People linked to an entry cap it like people tagged in a document; linking a
  protected living person, or making a linked person more private, narrows the entry.
- **Review.** Proposals are applied as the proposer (ADR-0021), so a proposal by a non-owner to
  change who may read an entry fails when approved (403) and the entry is unchanged. Nobody but the
  owner may propose a change to a private entry (403), and a proposal about an entry that becomes
  private is hidden from everyone who can no longer read it, its proposer included; it reappears if
  the entry is shared again. While hidden it cannot be decided.
- **Changes (§10).** A private entry is edited and withdrawn by its owner alone: members it is
  shared with read it, whatever their role (`can_edit`, `can_withdraw` say so). Revoking a grant,
  removing a member from the sharing panel, narrowing to Only me, withdrawing the entry or a grant's
  expiry all end access on the next request (§7).
- **Audit (§11).** Events about an entry the reader is not in the audience of are shown as an opaque
  `private_record` entry. A withdrawn entry that was shared keeps its history visible.
- **API.** `GET|PUT /traditions/{id}/sharing`, `POST …/sharing/preview`; `TraditionOut.is_owner`,
  `can_edit_sharing`.
- **UI.** The tradition editor picks the audience for a new entry with Visibility & Sharing
  (without download controls); an entry's page has the same `RecordSharingPanel` as documents.
- **Tests.** `tests/test_traditions_sharing.py` (12 cases, including the migration and its
  downgrade), a component test for records without downloads, and a second Playwright test in
  `record-sharing.spec.ts`; threat model T57.

## Implementation notes (9 Nov 2026, increment 3: event photo albums)
- **Choosing at upload.** `POST /events/{id}/media` accepts the record audiences, a branch and
  `allow_download`. Without a choice: Only me (no download) when a protected living person is in
  the photo (the event's principal included), per §9; otherwise ADR-0015's inheritance (the
  strictest of the tree default, the event and its principal), unchanged.
- **The event is a ceiling (§5.3).** `core.event_cap` maps the event's level like a person's.
  `DocumentRecord.extra_caps` adds the event of every album a photo is in, so sharing a photo wider
  than its event is refused (`422 privacy_too_open`) at upload and later. Making an event more
  private narrows its photos (`core.enforce_event_ceiling`, from `update_event`), as a person's
  privacy narrows the records they are tagged in.
- **Linking an existing photo** into an album that is more private than the photo is refused:
  adding a photo to an album never narrows someone's photo silently; its owner narrows it first.
- **Album × photo (§6)** was already enforced in increment 1 (listings, counts, covers through
  `can_view_document`); tests now cover the per-viewer cover with Selected members.
- **UI.** The album's upload form keeps the default and offers "Choose who can see this photo",
  which opens Visibility & Sharing; each photo shows its badge and, for its owner, a "Who can see"
  link to the photo's sharing panel.
- **Tests.** `tests/test_album_sharing.py` (6 cases), a third Playwright test in
  `record-sharing.spec.ts`; threat model T58.

## Implementation notes (9 Nov 2026, increment 4: standalone photo collections)
- **Model.** `photo_collection` (a shareable record: title, description, record audience, owner
  membership, branch audience; new collections are Only me) and `photo_collection_item` (a photo,
  caption, order, cover), both tree-scoped with row-level security; `GrantResource.COLLECTION`.
  Migration `b5c1e7a93d42`, with a downgrade that deletes collection grants and drops both tables.
- **Album × photo (§6).** A viewer sees an item only when they may see the collection and the
  photo; lists, counts and covers are per viewer. Adding a photo never changes who can see it, and
  sharing a collection never shares its photos. The owner is told how many photos part of the
  collection's audience cannot see (`items_not_shared`, and a flag on each item).
- **Who may change what (§10).** Only the owner changes the contents, title or description, or
  deletes the collection (its photos stay in the vault). Sharing uses the shared core through a
  `CollectionRecord` adapter: the owner widens with confirmation, admins only narrow; no download
  right at collection level (downloads belong to each photo). Only photos the owner can see can be
  added; never another tree's.
- **Audit (§11).** Audit-log redaction now covers documents, traditions and collections. This also
  closes a gap from increment 2: entries about a private tradition named it to admins.
- **API.** `/trees/{id}/collections` (list, create), `/collections/{id}` (get, patch, delete),
  `/collections/{id}/items` (add, patch, remove), `/collections/{id}/sharing` (+ `/preview`).
- **UI.** "Photo collections" in the family menu: list with per-viewer covers and counts, a new
  collection dialog with Visibility & Sharing, a detail page with a photo picker, cover, removal,
  the not-shared warning and the sharing panel.
- **Tests.** `tests/test_photo_collections.py` (7 cases), page tests in `CollectionsPage.test.tsx`,
  a fourth Playwright test in `record-sharing.spec.ts`; threat model T59.

## Implementation notes (9 Nov 2026, increment 5: ownership transfer and remaining paths)
- **Ownership transfer (§2)** for documents, tradition entries and photo collections:
  `pending_owner_membership_id` (migration `e4b8c2d6f913`, after the photo collections). The owner
  offers (`POST /trees/{id}/records/{type}/{rid}/ownership-offer`), the member accepts
  (`…/accept`) or declines, the owner may cancel (`DELETE …`); `GET /trees/{id}/ownership-offers`
  lists offers to the caller. An offer gives no access; it lapses if the member leaves (SET NULL).
  Grants stay with the record and are managed by the new owner. Audited as
  `record.ownership_offered`, `record.ownership_transferred`, `record.ownership_declined`,
  `record.ownership_offer_cancelled`, without titles, and redacted like any record event. Anyone
  but the owner or the member offered the record gets 404; an orphaned record cannot be offered or
  claimed. There is no UI for transfers yet.
- **Render files** open for their requester only: a render may embed the requester's private
  photos. Tree admins still see other members' jobs.
- **Consent evidence** is checked with document visibility, so naming a hidden document answers
  404 like a missing one.
- **`level_allows` denies by default:** a level no rule names admits nobody (before, it admitted
  any member). No current level reaches that branch.
- Tests: `tests/test_record_ownership.py`, `test_render_jobs.py`, `test_migrations.py`; threat T60.

## Implementation notes (9 Nov 2026, increment 6: collections in search and the archive export)
- **Search.** A `collection` search provider matches the title or description of the collections
  the searcher may see (`collection_allows`, so no role reaches a private one, and a private
  collection's description never produces a hit). Hits link to the collection page; the `kinds`
  filter and the search page offer "Photo collection".
- **Archive export.** `collections/index.json` lists the exporter's view: only collections they may
  see and, inside each, only photos they may see (`can_view_document` per photo), with caption,
  cover and order. Photos are referenced by document id; `in_documents_index` says whether that
  photo is in `documents/index.json` of the same export. The manifest counts collections. No new
  bytes are exported: a photo's file is still included only under the document rules.
- **No schema change**, no migration.
- **Tests.** `tests/test_collections_export_search.py` (search by role and audience, the owner's,
  the tree owner's and the author's export); threat model T59 extended.

## Implementation notes (9 Nov 2026, increment 7: telling owners about automatic narrowing)
- **Owner notice (§5, "and tells the owner").** When `enforce_ceiling` narrows a document or a
  tradition entry (a private person tagged or made private, an album's event made private, an
  erasure, a hidden profile), the record's owner gets an in-app notice: kind `document_narrowed` or
  `tradition_narrowed` and the record's id, nothing else. The actor is not stored, so the notice
  never says who caused it or why. No notice when the owner narrowed it themselves or has left the
  tree; at most one unread notice per record. The text is built when read and quotes the title only
  while the reader may still see the record; the notice links to the record. Photo collections are
  never narrowed automatically (they tag nobody), so they have no notice.
- **Hidden during a claim review.** "This is me, remove me" through a claim link hides the profile
  (ADR-0011) and now narrows the documents and traditions tagging it at once, run as the system
  (no actor in the audit; reason `person_privacy`, the same as any privacy change, so the owner
  never learns of the request). The link holder is not a member and gains nothing. Declining the
  request restores the profile but never widens a record again; its owner decides.
- **Migration** `c7e3a1f5b829` (after `e4b8c2d6f913`) adds the two kinds to the notification
  check constraint; the downgrade deletes those notices first.
- **Tests.** `tests/test_narrowing_notices.py` (6 cases), Vitest `ReviewParts.test.tsx`; threat
  model T61.

## Implementation notes (9 Nov 2026, increment 8: takedown, suspension and appeals)
Implements "Takedown in detail" above (the owner's decisions of 9 Nov 2026); the ADR's status is
unchanged and legal-request routing stays open.
- **Model.** `record_report` (reference, record type and id, reason, the reporter's note, the
  reporter's membership, status and review) and `record_suspension` (report, record, who suspended,
  status, appeal note, appeal and due dates, escalation, who decided, when, reason code, note,
  `sole_reviewer`), both tree-scoped with row-level security; `suspended_at` on `document`,
  `tradition_entry` and `photo_collection`; permission `record.takedown` (owners, family admins);
  seven notification kinds. Migration `d9b4f2c6a713`, with a downgrade that removes them.
- **Enforcement.** `can_view_document`, `entry_allows` and `collection_allows` check `suspended_at`
  first (owner only), so every route that already used them (detail, lists, albums, collections,
  search, export, signed links, sharing) follows. `core.apply` refuses widening and
  `create_grant` refuses new grants while suspended (409 `record_suspended`); widening is judged
  on the record's own audience, as if it were not suspended.
- **Lifting** clears `suspended_at`, then re-runs `enforce_ceiling`; grants, levels and links are
  read as they are now.
- **Offers at suspension (detail 9, option 1).** `suspend` locks the record row
  (`SELECT … FOR UPDATE`, re-read) and, in the same transaction, clears
  `pending_owner_membership_id` and writes `record.ownership_offer_cancelled` with no actor and
  details `{"by": "system"}`. Every ownership change (`offer`, `accept`, cancel or decline) locks the
  same row first, so the two are serialised by the database. A suspended record is refused a new
  offer (409 `record_suspended`, to its owner, who knows); acceptance answers the same 404 as any
  missing offer; `GET /ownership-offers` never lists a suspended record. The owner's suspension
  notice says any offer was cancelled; the offered member gets no notice, as when an owner cancels.
- **Audit of suspended traditions.** `entry_audience_allows` (the audit log's check for tradition
  events) now also hides a suspended entry from everyone but its owner.
- **API.** `POST /trees/{id}/records/{type}/{id}/reports`; `GET /record-reports`,
  `POST /record-reports/{id}/dismiss`, `POST /record-reports/{id}/suspend`;
  `GET /record-suspensions` (+ `/{id}`), `POST /record-suspensions/{id}/appeal`,
  `POST /record-suspensions/{id}/decision`. Overdue appeals are escalated when suspensions are read.
- **Not built:** a takedown screen (API and notices only), legal-request routing (open).
- **Tests.** `tests/test_record_takedown.py` (11 cases) and `tests/test_takedown_ownership.py` (7
  cases, two of them with two real database transactions in each order); threat model T62.

## Proposed amendment (9 Nov 2026, PR #51 follow-up): ownership recovery and rollback — **not accepted**
Status: **Proposed.** Everything below waits for the owner's review; the decisions D1–D5 are listed
in `docs/operations/tradition-ownership-recovery.md` §6 with options and a recommendation. The code
in this follow-up only enforces what §2, §3 and §10 already say, plus fail-closed rollback safety.

- **Findings verified** (tests in `tests/test_tradition_ownership_recovery.py`): an orphaned private
  entry is unreadable by every role on every route and stays with its grantees (as §2 says); a
  re-invited author or recipient gets no ownership, grant or offer back (as §3 says). Not as the
  ADR says: (1) an offer made before the owner left could still be accepted, so an orphan *could*
  be claimed; (2) a tree admin could narrow an orphan to Only me, leaving it readable by nobody;
  (3) the previous release, run on the new schema by `rollback.sh`, writes `PRIVATE_SELF` without an
  owner, which the record evaluator shows to the tree OWNER and not to the author; (4) the downgrade
  of `8d2e6b4f1a37` widens Selected members to admins, discards grants and transfers, and lets a
  re-upgrade make a re-invited author the owner again.
- **Enforced now:** (1) an offer cannot be accepted or listed once its owner's membership is gone;
  (2) Only me is refused on an ownerless record (`422 orphan_only_me`); (3) migration `f2a9c4e7d815`
  narrows leftover tradition `PRIVATE_SELF` to `ONLY_ME`, and a trigger stores any future
  `PRIVATE_SELF` as `ONLY_ME` and gives an entry inserted without an owner its author's current
  membership; (4) the same migration refuses, atomically and with counts only, a downgrade that
  would run `8d2e6b4f1a37`'s downgrade while that would change who can read or own an entry.
  `8d2e6b4f1a37` itself is not edited.
- **Proposed, not decided:** a recovery path for authors who return (D1, recommended: none now,
  pre-departure "keep for me" next); whether entries backfilled to an author re-invited before the
  upgrade stay owned (D2, recommended: yes); what to do about ownerless rows written by old code
  before `f2a9c4e7d815` (D3); whether a refused downgrade may ever be overridden (D4, recommended:
  no — restore from backup instead). Admin reassignment or admin read access to orphans is **not**
  proposed (§8).
- **Same shape elsewhere, not changed here:** documents (`3f6a8c1d2e94`) and photo collections
  (`b5c1e7a93d42`) have unguarded lossy downgrades, and documents written by pre-ADR-0027 code are
  ownerless.
