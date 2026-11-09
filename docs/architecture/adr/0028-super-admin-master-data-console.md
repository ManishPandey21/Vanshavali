# ADR-0028: Super Admin master-data console: global terms published from the interface (Option B)

- Status: **Proposed** · Date: 2026-11-09 · Not implemented. Nothing in this ADR is built until the
  owner accepts it.
- Would amend, **only once accepted**:
  - ADR-0006 §6: system administrators get a separate master-data capability.
  - ADR-0018 §4: the packs stop being the only source of truth for global terms.
  - ADR-0026 §4 and its open point "Where curation happens": curation moves from the operator CLI
    and code review to the console.

  Those accepted ADRs are **not** edited or marked superseded by this proposal. If it is accepted,
  each gets a short "amended by ADR-0028" note in a separate, reviewed change.
- Relates to: ADR-0002 (roles and row-level security), ADR-0005 (sign-in, two-step sign-in),
  ADR-0019 (geography snapshots), ADR-0021 (review and revisions), ADR-0025 (transliteration
  lexicon), Q4 (caste, jati and religion), Q13 (lawful basis).
- Prior work:
  - PR #35 (draft) built a console on an older schema. It stays open as a reference; this ADR
    reuses its ideas, not its code.
  - PR #19 (draft) is unrelated to this decision and is left untouched.

## Context

### What `main` does today (verified 9 Nov 2026, `1f99b97`)
- **Global terms live in JSON packs** (`backend/app/modules/masterdata/packs/*.json`). There are nine
  vocabularies: gotra (16 terms), kula (7), occupation (17), honorific (8), language (23, closed),
  pravara (14 gotra links, all `draft`), and kuladevata, kuladevi and devak, which are empty.
- **The loader is the only writer.** `python -m app.cli.masterdata load` runs as the schema owner,
  after `alembic upgrade`, in:
  - the pilot `migrate` service (`deploy/pilot/compose.yml`);
  - `make migrate`;
  - CI;
  - the e2e database reset;
  - the test fixtures, through `owner_session()`.

  It inserts new terms, **overwrites every changed field of an existing term**, and retires terms
  missing from a pack. No API route writes `vocabulary` or `vocabulary_term`. So today any edit made
  in the database would be undone by the next deploy.
- **Families' own entries** are in `tree_vocabulary_term`, which is tree-scoped under row-level
  security. A tree admin may offer one to the common lists (ADR-0026 §4).
  - The offer carries the label, aliases, an optional temple name and a free-text note of up to
    500 characters.
  - The tree and the offerer are stored on the row.
  - Operators decide offers with `python -m app.cli.masterdata offers`. Accepting writes into the
    pack JSON, so the change then goes through code review.
- **Grants.** The application role (`vanshavali_app`) has `SELECT, INSERT, UPDATE, DELETE` on every
  table except the four geography tables, which `GRANT_APP_ROLE_SQL` makes read-only
  (`app/models/rls.py`, ADR-0019 §2). That includes `vocabulary` and `vocabulary_term`.
- **Administrators.**
  - `app_user.is_system_admin` is a single flag. ADR-0006 §6 limits it to health and metrics, plus
    seeing draft kinship packs.
  - The demo seeder creates `superadmin@example.com` with the flag, but only in development and
    test.
  - Two-step sign-in (TOTP) exists and is optional. When it is on, Google sign-in is refused for
    that account.
  - Nothing records whether a session was opened with the second step.
- **Geography** (LGD units and PIN offices) is loaded as reviewed snapshots by an operator CLI.
  Only synthetic fixtures are committed, and the licensing of the real files is still open.

### The decision asked for
The owner chose **Option B**: authorised administrators create and change supported global terms
in the interface, and the change takes effect without a code deployment.

Option A was the alternative:
- the console only drafts changes;
- a CLI writes them into the packs;
- code review publishes them.

Option B removes code review as the gate. So this ADR has to put a review step into the
application itself, and decide what happens when a pack and the database disagree.

## Decision

### 1. Which data the console may change
Only the **extensible reference vocabularies** whose terms are typing aids are editable (§13 lists
every category).
- Controlled values and closed astronomical sets stay in code.
- Authoritative external datasets (geography and PIN codes) are never edited term by term.
- Optional personal fields (religion, community, caste or jati) get **no** global list, in the
  console or anywhere else (Q4, ADR-0018 §2).
- The console cannot create a new vocabulary, and cannot change which vocabularies exist. That
  stays a code and migration change.

### 2. Source of truth: decided per vocabulary, not per term
`vocabulary` gains `authority`, which is either `pack` or `database`.
- **`pack`** is today's behaviour and the default for every vocabulary.
  - The pack in the repository is the source of truth.
  - The console shows the vocabulary read-only.
  - The loader behaves as it does now, except that it never touches a curated term (§3).
- **`database`**:
  - The database is the source of truth.
  - Console changes, once approved, are what families see.
  - The pack becomes a **seed and proposal channel**. New pack terms are proposed, never applied
    over a curated term (§3).
  - Moving a vocabulary from `pack` to `database` (adoption), or back (§11), is itself a change
    that needs a second administrator's approval. It is recorded in the history.
- Proposed first adopters: gotra, kula, kuladevata, kuladevi, devak and occupation. Honorific and
  pravara could follow. Language stays `pack`, because it is a closed list.

Per-vocabulary authority means one answer to "where is the truth for this list?". The alternative,
a "curated" flag on each term, leaves every list half in Git and half in the database (see the
alternatives).

### 3. Loader behaviour (`python -m app.cli.masterdata load`)
**Unchanged:**
- it runs as the schema owner;
- it is idempotent;
- the whole run is one transaction, so an invalid pack loads nothing;
- it never deletes a term.

**New:** a term is **curated** once any console change to it has been published. A term first
created by the console is curated from the start.

| Pack | Database | Vocabulary authority | Loader action |
|---|---|---|---|
| has term, not in DB | — | `pack` | Insert (as today). |
| has term, not in DB | — | `database` | Insert only if the code was never used. The term starts `draft`, outside suggestions, and appears in the console as a **pack proposal**. A code the console retired or reserved is never re-created; it is reported as a conflict. |
| has term, differs | not curated | `pack` | Update (as today). |
| has term, differs | not curated | `database` | Report as a pack proposal; no write. |
| has term, differs | **curated** | either | **Never overwritten.** Reported as a conflict ("pack differs from curated term"). The console offers it as a proposed change, which goes through the normal approval. |
| term missing | not curated | `pack` | Retire (as today). |
| term missing | not curated | `database` | No change; reported. |
| term missing | **curated** | either | No change; reported. |
| vocabulary metadata (description, version, source, licence) | — | `pack` | Update. |
| vocabulary metadata | — | `database` | Keep the database values; record the pack version as `pack_version_seen`. |

- **Locking.** The loader and console publication take the same transaction-scoped advisory lock,
  so a deploy can never interleave with a publish.
- **Reporting.** `--dry-run` prints the same report, including conflicts. CI fails if
  `load --dry-run` reports a conflict for a vocabulary whose authority is `pack`. That would mean a
  curated term is shadowing the pack in a pack-owned list, which should not happen.
- **History.** Every insert, update or retirement the loader makes is written to the version
  history (§5), with `source = loader` and the pack version.

**How curated data survives pack loads and upgrades:**
1. The loader never writes a curated term (table above), and is tested against a database with
   curated terms in every state.
2. Migrations that touch `vocabulary` or `vocabulary_term` must keep every row and every curated
   value. A migration test upgrades a database seeded with curated, retired and pack-proposed terms
   and checks they are unchanged.
3. `masterdata export --vocabulary <key>` writes a vocabulary's current database state as a pack
   file, with its history in a sidecar file.
   - The release runbook runs it before every deploy and keeps the output with the backup.
   - It can also be committed, so the repository catches up with the console by code review
     whenever the owner wants.
4. Backups are already point-in-time (ADR-0014). Nothing in a deploy truncates or reloads these
   tables.

### 4. The change workflow
**Change types:** create a term, edit labels, aliases, scope, attributes or source, retire,
reactivate, merge, and adopt or release a vocabulary (§2).
- Each change request records the term, the term's **base revision**, the proposed values and a
  required reason.
- At most **one open change per term**, enforced by a partial unique index.

**States:** `draft` → `submitted` → `approved` (publishes at once) | `rejected` | `withdrawn` |
`stale`.

**Approval:**
- **A second, different administrator** approves.
- The rule is enforced in the service and by a database `CHECK (approved_by <> submitted_by)`.
- **There is no self-approval path in the interface or the API**; §7 describes the only exception
  and how it is kept visible.

**Publication:**
- Approval publishes in one transaction under the advisory lock.
- It re-validates the term (§9).
- It checks that the term's current revision equals the base revision. Otherwise the change becomes
  `stale` and must be rebased by its author.
- It writes the term, the version (§5) and the audit event (§6).

**Rejection** carries a short reason, visible to the author only.

### 5. Version history
- **New table `vocabulary_term_version`**, one row per published revision of a term:
  - a complete copy of the term's fields;
  - `revision`;
  - `source`: `console`, `loader` or `export_import`;
  - the change request id;
  - submitted-by and approved-by user ids;
  - the approval mode (`second_admin`, `solo` or `loader`);
  - the time.
- **Append-only.** A trigger refuses UPDATE and DELETE, as on `audit_event`.
- **The term itself** carries `revision`, `curated` and `replaced_by` (merges, §10).
- **Rollback of a term** means proposing a change that restores an earlier version. It is approved
  like any other change. History is never rewritten.

### 6. Audit trail
Every action writes an `audit_event` with `tree_id = NULL`:
- `masterdata.change_submitted`, `…approved`, `…rejected`, `…withdrawn` and `…published`;
- `masterdata.vocabulary_adopted` and `…released`;
- `masterdata.solo_mode_enabled`, `…disabled` and `…solo_published`;
- `masterdata.capability_granted` and `…revoked`;
- `masterdata.offer_accepted` and `…declined`;
- `masterdata.loader_conflict`.

**`details`** holds vocabulary keys, term codes, change ids, the names of changed fields and the
approval mode. Global term labels are public reference data and may be included.

**It never holds:**
- a tree id;
- an offerer;
- an offer note;
- anything taken from a family's records.

**Who sees master-data audit events:** administrators with the capability, in the console. Tree
audit logs stay with tree owners and admins (ADR-0006), and the console cannot read them.

### 7. Administrators, sign-in and authorisation
- **A separate capability.** `master_data.admin` lives in a new `platform_capability_grant` table
  (user, capability, granted by, granted at, reason, revoked at). It is not the `is_system_admin`
  flag.
  - Grants and revocations are made **only by the operator CLI**, as the schema owner, and are
    audited.
  - The demo seeder never grants it.
  - The CLI refuses an account without a verified email and two-step sign-in.
- **Named accounts only.**
  - One person per account. The grant records the person's name and the reason.
  - Shared or role mailboxes (for example `admin@`, `ops@`, `info@`) are refused by the CLI. They
    are listed in a configurable deny-list.
  - The pilot runbook forbids shared credentials.
- **Two-step sign-in is required.**
  - `user_session` gains `mfa_verified_at`, set only when the session was opened with a password
    plus TOTP.
  - Every console request needs a session with it set, opened within the last 12 hours.
  - Approve, publish, adopt and every solo action need a TOTP code entered in the last 15 minutes
    (step-up).
  - Turning off two-step sign-in removes console access at once, because it is checked on every
    request rather than cached.
- **Server-side authorisation.**
  - Every `/api/v1/admin/master-data/*` route depends on `require_platform(MASTER_DATA_ADMIN)`.
  - A caller without the capability gets **404**, so the console's existence isn't revealed.
  - A holder without a valid second step gets 403 `admin_mfa_required`.
  - Writes need the CSRF header and are rate-limited.
  - The UI only hides controls; the server decides.
- **Single-admin installation (separate, auditable option).** Until a second administrator exists,
  a change cannot be approved. That is the default and recommended state. For a one-admin pilot,
  the owner may turn on **solo mode**, which is deliberately *not* self-approval in the normal flow:
  - **Turning it on or off** is an operator CLI command run on the server as the schema owner. It
    records who ran it, the reason and an expiry of at most 90 days. It is never available in the
    web interface.
  - **It switches itself off** as soon as two administrators hold the capability, and when it
    expires.
  - **A solo publication**:
    - waits at least **24 hours** after submission;
    - then needs the same administrator to confirm, with a fresh TOTP code and a typed
      confirmation;
    - is recorded with `approval_mode = solo`, in the version history and in a
      `masterdata.solo_published` audit event.
  - **Visibility.** While solo mode is on, the console shows a permanent banner. Every
    solo-published term is listed under "Published without a second reviewer". When a second
    administrator joins, that list becomes their first review queue: each item is confirmed or
    reverted by an ordinary approved change.
  - **Alternative for the owner to weigh:** no solo mode at all. A one-admin installation then
    drafts in the console, and the operator publishes by CLI, as in Option A.

### 8. No access to family trees
The capability is a platform permission and grants **no tree permission of any kind**.
- **No tree binding.** Console handlers never bind `app.tree_id`, so row-level security returns
  nothing from tree-scoped tables.
- **No tree code.** Console code may not import tree-scoped models or tree services. A new test
  will check this by parsing the console module's imports; no such test exists yet.
- **Same tree rules as everyone.** An administrator with the capability gets the same 404 as any
  non-member on every `/trees/{id}` route. Their own family memberships work as for anyone, and
  nothing more.
- **Offers are the only family-originated data the console sees.** It reads them only through the
  narrow projection in §12. It never sees:
  - which tree or person an offer came from;
  - how a term is used;
  - how many families use it.

### 9. Validation
One validator serves both pack files and console changes. It extends `loader.validate_pack`.
- **Codes.** Must match `^[a-z0-9][a-z0-9_]{0,79}$`. They are immutable once published and never
  reused, even after retirement.
- **Labels.**
  - English and Hindi labels are required.
  - Text is normalised to NFC and length-limited (labels 200, aliases 200 each, at most 20
    aliases).
  - Refused: control characters, bidirectional overrides, HTML and markup.
- **Duplicates.** None within a vocabulary across scripts and spellings (`match.same_value`, the
  same check offers use). A near-duplicate is shown as a warning, and the approver sees it.
- **Structure.**
  - `parent` must exist (a pravara link names a gotra).
  - A `reviewed` pravara link needs a cited source and a named reviewer (ADR-0026 §3).
  - Closed vocabularies (language) cannot gain or lose terms; only labels can change.
- **No "Unknown" or "Not applicable" terms** (ADR-0018 §2).
- **Personal-data screening** on every label, alias and attribute. Flagged and blocked until edited:
  - email addresses, URLs and phone-like digit runs;
  - five or more digits in a row;
  - `@` handles;
  - words such as "family of", "s/o" and "d/o".
- **Category guard.** The vocabulary key must be one of those §13 marks console-editable. A request
  naming any other key is refused with 404, so it cannot be used to create a list.
- **No automatic checking for prohibited content.** No validator can reliably spot a caste or
  religion category disguised as a gotra. That is what the second administrator is for, and the
  approval screen asks the question explicitly.

### 10. Retirement, merging and stored values
- **Retiring** hides a term from suggestions. Stored references keep resolving, because records
  store the label and the code (ADR-0018 §6). Reactivation is an ordinary change.
- **Merging** two terms retires one with `replaced_by` pointing at the other. Search then returns
  one result. **Stored family values are never rewritten**: a family that picked the retired code
  keeps its label and code.
- **Nothing is ever deleted through the console**, and codes are never reused.

### 11. Rollback
- **One term:** propose a change restoring an earlier version (§5).
- **A whole vocabulary to the repository:**
  1. `masterdata export` (§3);
  2. commit the export by code review;
  3. *release* the vocabulary (an approved change, `database` → `pack`).

  After that the loader owns it again. Releasing never re-applies an old pack over curated terms
  by itself. To do that, the operator runs `load --adopt-pack <key>`, which shows a diff and needs
  `--confirm`.
- **Switching the console off:** `VSH_MASTERDATA_CONSOLE_ENABLED=false` makes every console route
  answer 404. Published terms stay, and families see no change. `VSH_MASTERDATA_ENABLED=false`
  still turns suggestions off altogether (ADR-0018 §7).
- **Migration downgrade:**
  - It drops the new tables and columns. Every term row and every published value stays in
    `vocabulary_term`.
  - It refuses to run while a change is `submitted`.
  - The runbook requires a `masterdata export` first, because the downgrade loses the version
    history.

### 12. Family offers in the console
**What the reviewer sees** is only what is needed to review a term:
- the vocabulary;
- the offered label and aliases;
- the optional temple name;
- the month the offer was made;
- matches against existing terms and other pending offers (so duplicates can be merged), with no
  count of families.

**What the reviewer does not see:**
- the tree, the offerer or their account;
- the exact time;
- the **free-text note** (below);
- any record that uses the entry.

**How the console reads and decides offers:**
- The tree-scoped table is read through a `SECURITY DEFINER` function owned by the schema owner.
  It returns only those columns, has a pinned `search_path`, and the application role may only
  EXECUTE it.
- Accepting or declining goes through a second definer function. It sets `offer_status` and
  `promoted_code` and writes the in-app notification to the offerer, inside that tree.
- So console code never binds a tree.

**Accepting an offer:**
- Accepting creates a **change request** prefilled from the offer. The administrator must review
  the label, may edit it, and adds the Hindi or English label.
- It is approved like any other change.
- **The published term is the administrator's text, never a copy of the offer.**

**Can free-text fields contain identifying information? Yes.** Assessment:

| Field | Limit | Risk | Decision |
|---|---|---|---|
| `offer_note` | 500 characters, any text | **High.** The likeliest place for "our Patil family of Wadgaon, call 98…", a person's name or a village. Nothing stops it today. | **Never shown in the console.** It stays visible to that tree's own admins, as today. Proposal for the owner: stop collecting the note for new offers, or replace it with a fixed "kind of entry" choice. That needs an ADR-0026 §4 change. |
| `label`, `aliases` | 200 each | **Medium.** A family-specific deity name, or a label such as "Sharma family Devi", can point to one family. | Shown, because it is the thing reviewed. It goes through the §9 screening, and flagged text is shown masked until the reviewer opens it (an audited reveal). The administrator writes the published label. A label that identifies a family is declined, or rewritten generically. |
| `offer_temple` | 200 | **Low to medium.** It names a public place, but a rare deity plus a village temple can narrow down a family. | Shown. It is published only if the administrator keeps it, as `attributes.temple`. Screened like labels. |

**Declining** tells the family only "not added to the common list" (ADR-0026 §4). It never gives a
reason that refers to other families.

### 13. Category decision table

Kinds of data:
- **R** = editable reference data;
- **X** = authoritative external dataset;
- **C** = controlled or closed set in code;
- **P** = optional personal field (no list).

| Category | Kind | Source of truth under this ADR | Console | Approval | Notes |
|---|---|---|---|---|---|
| **Geography (LGD units)** | X | Activated LGD snapshot (ADR-0019) | Read-only. No term edits. Snapshot staging stays in the operator CLI. | — | **No official data is imported until its source and licence are resolved** by the owner. Only synthetic fixtures today. |
| **Geography aliases** | R (curated) | `geo/aliases.json`, by code review | Read-only (could adopt later by its own ADR) | — | Never a family's spelling. |
| **PIN codes (India Post)** | X | Activated snapshot | Read-only | — | Same licensing gate. A PIN suggests a district and state, never a village or a person's address. |
| **Gotra** | R | `database` once adopted | Create, edit, retire, merge; offers | Second admin | No inference: a gotra never implies community, region, religion or pravara (ADR-0026 §3). |
| **Kula / vamsha** | R | `database` once adopted | As gotra | Second admin | |
| **Kuladevata, Kuladevi** | R | `database` once adopted | As gotra, with an optional temple attribute | Second admin | The lists start empty and grow from offers. |
| **Devak** | R | `database` once adopted | As gotra | Second admin | |
| **Pravara (gotra links)** | R (sourced links) | `pack` at first | Read-only at first; later edit with a required source and reviewer | Second admin | A link is suggested only when `reviewed` with a cited source. Never filled in from a gotra. |
| **Occupation, Honorific** | R | `database` once adopted | Create, edit, retire | Second admin | Fields stay free text. |
| **Language** | C (closed list of 23) | `pack` | Labels only, after adoption; no additions | Second admin | `allows_custom = false`. |
| **Rashi** | C (12, closed, astronomical) | `astrology/vocab.py` | **Read-only** | Code review | Used for validation and calculation. An edit could break both. |
| **Nakshatra** | C (27, closed) | `astrology/vocab.py` | **Read-only** | Code review | As rashi. |
| Tithi, paksha, ayanamsha | C | `astrology/vocab.py` | Read-only | Code review | |
| Kinship word packs | C (reviewed language data) | `kinship/packs/*.json` | Not in the console | Native-speaker review, then code review (ADR-0026 §6) | Out of scope. |
| Transliteration lexicon | C | ADR-0025 files | Not in the console | Code review | Out of scope. |
| **Religion** | P | The family's own free text | **No list, no console** | — | Q4, ADR-0018 §2. Nothing about a person's beliefs is inferred from a name, gotra, deity, place or any other field. |
| **Community** | P | Free text | **No list, no console** | — | As religion. |
| **Caste / jati** | P | Free text, private field group | **No list, no console** | — | As religion. Never derived from surname, gotra or place. |
| Roles, privacy levels, relationship types, statuses | C | `enums.py` | Not in the console | Code | ADR-0018 §1. |

- **Adding a category or changing its kind** is a code change with an ADR. The console cannot do
  either.
- PR #35's proposed ADR-0018 amendment 2 (optional religion and community suggestions) is **not**
  adopted here. If wanted, it needs its own decision under Q4.

### 14. The application's database write privileges
**Investigation (9 Nov 2026, on `main`):**
- **Who writes these tables today.** Only the loader writes `vocabulary` and `vocabulary_term`. It
  runs as the schema owner in every environment: the pilot `migrate` service with the owner URL,
  `make migrate`, CI, `e2e/scripts/reset_db.py` (before `ensure_app_role`), and the test fixtures
  through `owner_session()`. No API or worker code writes them.
- **Experiment.** The application role's `INSERT, UPDATE, DELETE, TRUNCATE` on both tables was
  revoked in a throwaway worktree, by adding them to the read-only array in `GRANT_APP_ROLE_SQL`,
  and the full backend suite was run against it. **Nothing on today's runtime path needs those
  writes.** Details are in the implementation notes below.
- **Effects of revoking:**
  - Today it breaks nothing on the runtime path.
  - `tree_vocabulary_term` must stay writable: families add their own entries and make offers
    there.
  - Foreign-key checks from `tree_vocabulary_term` to `vocabulary` still work, because they run as
    the table owner.
  - Under Option B, revoking alone would **block console publication**, because the API connects
    as the application role. A path for publication is therefore needed.
- **Recommendation (proposed, not implemented):**
  - Make `vocabulary`, `vocabulary_term`, `vocabulary_term_version` and the change-request tables
    **read-only to the application role**. They join `READ_ONLY_TABLES`.
  - Publish only through a few `SECURITY DEFINER` functions owned by the schema owner, with a
    pinned `search_path`, that the application role may EXECUTE: `masterdata_publish_change`,
    `masterdata_submit_change`, `masterdata_decide_offer`, and the two offer projections in §12.
  - These functions repeat the essential checks inside the database:
    - the approver differs from the author, unless the solo-mode row is active and 24 hours have
      passed;
    - the base revision matches;
    - the vocabulary's authority is `database`;
    - nothing is ever deleted;
    - every change writes a version row.
- **What this buys:** a bug or an injection anywhere else in the API can no longer rewrite, delete
  or truncate the global lists, or skip the version history. Self-approval and deletion are refused
  even if the service layer is wrong.
- **What it does not buy:** the database cannot verify *who* the user is. Someone who fully
  controls the API process can still call the functions with forged user ids. Named accounts,
  two-step sign-in, the audit trail and the "published without a second reviewer" list are the
  controls for that.
- **The alternative,** a second login role only for the console, adds a credential that sits in
  the same process. It gains little over definer functions and complicates deployment.

## Threats and tests to write before code (threat T63)
Each of these becomes a test in the implementation PRs:
- **Privilege.**
  - A non-holder gets 404 on every console route.
  - A holder without a second-step session gets 403.
  - A holder whose two-step sign-in was turned off loses access on the next request.
  - A Google-only session never qualifies.
- **No tree access.**
  - A capability holder gets 404 on every `/trees/{id}` route of a tree they are not in. This
    reuses the parametrised route test.
  - Console handlers never bind a tree.
  - The new import-boundary test passes.
- **Self-approval.** Refused by the service and by the database CHECK and the definer function.
  Solo publication before 24 hours, without a fresh TOTP, or with solo mode off is refused.
  Solo mode switches off when a second admin is granted.
- **Concurrency.**
  - Two approvals of the same change: exactly one publishes.
  - A stale base revision returns 409.
  - A loader run during a publish is serialised by the advisory lock.
- **Loader.**
  - Curated terms are never overwritten, retired or re-created, in each row of the §3 table.
  - Pack proposals are not suggested.
  - CI fails on a conflict in a `pack` vocabulary.
- **Upgrade.** A migration round trip keeps curated, retired and proposed terms. The downgrade is
  refused while a change is submitted.
- **History and audit.**
  - Version rows cannot be updated or deleted.
  - Every publish has a version row and an audit event.
  - Audit details contain no tree id, offerer or note.
- **Offers.**
  - The projection returns no tree id, offerer, exact time or note.
  - A decision notifies only the offerer inside their tree.
  - Accepting publishes the administrator's text, not the offer's.
  - Screened text is masked, and each reveal is audited.
- **Validation.** Every rule in §9 has a negative test, including bidirectional and control
  characters, phone and email patterns, "Unknown" terms, closed-list growth, a pravara link without
  a source, and a non-editable vocabulary key.
- **Grants (if §14 is accepted).**
  - The application role cannot INSERT, UPDATE, DELETE or TRUNCATE the master-data tables.
  - The definer functions refuse self-approval and deletion even when called directly.
- **E2E.** An admin signs in with two-step sign-in, drafts a term, and a second admin approves it.
  A family then sees the suggestion without a deploy, and a family member gets 404 on the console.

The threat model (T63) and the privacy model (an "administrators and global lists" section) are
updated in the first implementation PR, not by this proposal.

## Consequences
- **One migration, with a downgrade:**
  - `vocabulary.authority` and `pack_version_seen`;
  - `vocabulary_term.revision`, `curated` and `replaced_by`;
  - `vocabulary_term_version`, `vocabulary_change_request`, `platform_capability_grant` and
    `masterdata_solo_mode`;
  - `user_session.mfa_verified_at`;
  - the definer functions and the grant changes, if §14 is accepted.
- **Loader:** it gains the curated rules, the reporting and the history writes.
- **New CLI commands:**
  - `masterdata export`;
  - `masterdata grant` and `revoke`;
  - `masterdata solo on` and `off`;
  - `load --adopt-pack`.
- **Frontend:** `/admin/master-data`, with lists, terms, history, the change queue, the offers queue
  and the solo banner. It is accessible, works at 390 px and is marked up for Indic scripts.
- **Operations:**
  - granting the capability and enrolling a second administrator join the go-live checklist;
  - `masterdata export` joins the release runbook.

## Alternatives considered
- **Option A** (the console drafts; a CLI writes packs; code review publishes). It keeps Git as
  the only truth and needs no in-app approval. **Not chosen by the owner**, because every change
  needs a deployment. It remains the fallback for a single-admin installation (§7).
- **Database publication without a second administrator.** Rejected. One compromised or mistaken
  account would change suggestions for every family at once.
- **A "curated" flag on each term, without per-vocabulary authority.** Rejected. Each list would be
  split between Git and the database, and nobody could say where its truth lives.
- **The loader overwrites the database, as today.** Rejected for Option B: every deploy would undo
  approved console work.
- **The console opens a pull request against the packs.** That is Option A with a robot. It still
  needs a deployment.
- **A separate admin service or database.** Rejected for the pilot (ADR-0001, modular monolith).
  The definer functions give most of the isolation.
- **Showing offerer and tree to reviewers** (ADR-0026 §4 as accepted lets operators see them).
  Rejected for the console: reviewing a term doesn't need them.

## Stress test
1. *Can a deploy undo an approved change?* No. Curated terms are never written by the loader, and
   conflicts are reported (§3).
2. *Can one administrator publish alone?* Not in the normal flow. Only in solo mode, which an
   operator turns on from the server. Solo publication waits 24 hours, needs a fresh second step,
   and is listed for later review (§7).
3. *Can a console admin read a family's tree?* No. There is no tree permission or tree binding,
   and the same 404 applies (§8). Offers come through a narrow projection (§12).
4. *Can an offer reveal which family uses a deity?* Reviewers never see the tree, the offerer, the
   note or any count. The published text is the administrator's own (§12).
5. *Can the console create a caste or religion list?* No. The set of editable vocabularies is
   fixed in code (§1, §9, §13). A disguised category inside an existing list is the second
   reviewer's question.
6. *What happens to stored values when a term is renamed, merged or retired?* Nothing. Records
   keep their label and code (§10).
7. *Two admins edit the same term at once?* There is one open change per term, a base-revision
   check, and the advisory lock (§4).
8. *How do we get back to Git as the truth?* Export, commit and release the vocabulary (§11).
9. *Is official geography data loaded through this?* No. It stays read-only and gated on licensing
   (§13).

## Open decisions for the owner
1. **Solo mode.** Accept it as specified (24-hour wait, at most 90 days, switched on by an operator
   CLI), change the numbers, or choose "no solo mode, CLI publication" instead (§7).
2. **The offer note.** Keep it hidden from the console only (proposed), or also stop collecting it
   for new offers, which amends ADR-0026 §4 (§12).
3. **Database privileges.** Accept §14 (read-only tables plus definer functions), or keep today's
   grants and rely on the service layer.
4. **First vocabularies to adopt** (proposed: gotra, kula, kuladevata, kuladevi, devak, occupation).
5. **Licensing of LGD and India Post data.** This is unchanged and still blocks any real geography
   import.

## Implementation plan (each a draft PR; none merged without the owner's approval)
1. **Platform capability and sign-in.**
   - `platform_capability_grant`, `mfa_verified_at`, the step-up, the grant and revoke CLI, and
     the no-tree-access tests.
   - The ADR-0006 note, threat T63 and the privacy-model section.
2. **Read-only console.** Lists, terms, history, the master-data audit log, and offers through the
   projection.
3. **History and loader.**
   - `authority`, `curated`, `vocabulary_term_version`, the loader rules, `export` and the
     upgrade tests.
   - If §14 is accepted: the grant changes and the definer functions.
4. **Change requests.** Second-admin approval, validation, retirement, merging and rollback.
5. **Solo mode,** if accepted.
6. **Offers in the console.** Prefilled change requests, screening and audited reveal.
7. **E2E specs and the runbook and go-live checklist updates.**

## Implementation notes
### 9 Nov 2026: the §14 experiment
The experiment was run in a throwaway worktree of `main` at `1f99b97`, against local
PostgreSQL 16. None of it was committed.

**The change tested:**
- `vocabulary` and `vocabulary_term` were added to the read-only array in `GRANT_APP_ROLE_SQL`.
- The grants then applied were checked directly. The test application role:
  - had `SELECT` on `vocabulary_term`;
  - had **no** `INSERT` on `vocabulary_term`; a direct `INSERT` failed with "permission denied
    for table vocabulary_term";
  - kept `INSERT` on `tree_vocabulary_term`.

**Full backend suite:** 704 passed, 4 skipped, 1 failed.
- The one failure was `test_geo.py::test_the_application_role_can_only_read_reference_tables`.
  That guard checks that the SQL array matches the `READ_ONLY_TABLES` constant, which the first run
  deliberately left unchanged.
- With the constant updated as well, the grant and master-data tests all pass:
  - `test_geo.py`;
  - `test_app_role.py`;
  - `test_masterdata.py`;
  - `test_heritage_depth.py`, which covers offers and curation.

**Conclusion:**
- Revoking the writes breaks nothing on `main` today.
- Families' own entries and offers keep working.
- Every loader path already runs as the schema owner.
- Under Option B, publishing from the console needs the definer functions in §14, because the API
  cannot write those tables once the grants are revoked.
- Not covered by this run:
  - the e2e suite;
  - a pilot `migrate` run. Its loader uses the owner URL, so it is expected to be unaffected.
