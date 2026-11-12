# ADR-0028: Super Admin master-data console: global terms published from the interface (Option B)

- Status: **Accepted** 2026-11-12, as amended · Date: 2026-11-09 · Amended 2026-11-11 (amendments
  A1–A10, see "Amendments of 11 Nov 2026" at the end) · Implementation in progress (increment 1 is
  draft PR #67). Open decisions 2–5 are still open; until they are settled the defaults in "Open
  decisions for the owner" apply.
- Amends:
  - ADR-0006 §6: system administrators get a separate master-data capability.
  - ADR-0018 §4: the packs stop being the only source of truth for global terms.
  - ADR-0026 §4 and its open point "Where curation happens": curation moves from the operator CLI
    and code review to the console.

  Those ADRs are not superseded. Each carries a short "amended by ADR-0028" note, added in a
  separate change (implementation plan, step 0).
- Relates to: ADR-0002 (roles and row-level security), ADR-0005 (sign-in, two-step sign-in),
  ADR-0019 (geography snapshots), ADR-0021 (review and revisions), ADR-0025 (transliteration
  lexicon), Q4 (caste, jati and religion), Q13 (lawful basis).
- Prior work:
  - PR #35 (draft) built a console on an older schema. The consolidation review
    (`docs/architecture/master-data-console-consolidation.md`, PR #64) compared it with this ADR
    file by file. This ADR reuses a named subset of #35's code (review §3), not its schema:
    #35's migrations `7d4a2c9e1b60` and `9e3b5d7f2a14` are **discarded, not re-parented**. They
    fork the Alembic graph, duplicate geography tables `main` already has, and encode the per-term
    model rejected in §2. #35 stays open as a reference until the increments in the implementation
    plan reach feature parity.
  - PR #60 carried #35's CI commits unchanged (same patch ids) and has merged on its own.
  - PR #19 (draft) is unrelated to this decision and is left untouched.

## Context

### What `main` does today (verified 9 Nov 2026 at `1f99b97`; re-verified 11 Nov 2026 at `5913759` and 12 Nov 2026 at `b8c248b`)
- **Global terms live in JSON packs** (`backend/app/modules/masterdata/packs/*.json`). There are nine
  vocabularies: gotra (16 terms), kula (7), occupation (17), honorific (8), language (23, closed),
  pravara (14 gotra links), and kuladevata, kuladevi and devak, which are empty.
- **Every live term is `draft`** (all 85). Family suggestions exclude only `retired` terms, unless
  a caller asks for `reviewed` only (`masterdata/service.py`, `_global_terms`). So **`draft` terms
  are suggested to families today**. A "not yet approved" term therefore cannot be stored as
  `draft` (§3, amendment A6).
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
  table except the five in `READ_ONLY_TABLES` (`geo_snapshot`, `geo_unit`, `geo_unit_alias`,
  `pincode_office`, `panchang_day`; `app/models/rls.py`, ADR-0019 §2). That includes `vocabulary`
  and `vocabulary_term`.
- **Row-level security is not FORCEd** (`app/models/rls.py`). The schema owner, and so any
  `SECURITY DEFINER` function it owns, bypasses every tree policy (§12, §14).
- **Administrators.**
  - `app_user.is_system_admin` is a single flag. ADR-0006 §6 limits it to health and metrics, plus
    seeing draft kinship packs.
  - The demo seeder creates `superadmin@example.com` with the flag, but only in development and
    test.
  - Two-step sign-in (TOTP) exists and is optional. When it is on, Google sign-in is refused for
    that account.
  - Nothing records whether a session was opened with the second step.
  - `UserOut` (the `/me` response) does not expose `is_system_admin`; the frontend cannot see the flag.
- **Geography** (LGD units and PIN offices) is loaded as reviewed snapshots by an operator CLI.
  Only synthetic fixtures are committed. The importer hard-codes the licence as GODL-India
  (`geo/importer.py`, `LICENCE`) with a fixed attribution; no legal review of that is recorded.

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
- First adopters (the owner's position, 11 Nov 2026): gotra, kula, kuladevata, kuladevi, devak and
  occupation. Honorific and pravara stay `pack`; adopting either later needs an amendment.
  Language stays `pack`, because it is a closed list.

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
| has term, not in DB | — | `database` | **No write to `vocabulary_term`.** Upsert a row in `vocabulary_pack_proposal`, only if the code is not used by any term, open change request or other proposal. It appears in the console as a **pack proposal** and is never suggested to families. A code the console retired or reserved is never re-created; it is reported as a conflict. |
| has term, differs | not curated | `pack` | Update (as today). |
| has term, differs | not curated | `database` | Upsert a `vocabulary_pack_proposal` row; no write to the term. |
| has term, differs | **curated** | either | **Never overwritten.** Reported as a conflict ("pack differs from curated term"). The console offers it as a proposed change, which goes through the normal approval. |
| term missing | not curated | `pack` | Retire (as today). |
| term missing | not curated | `database` | No change; reported. |
| term missing | **curated** | either | No change; reported. |
| vocabulary metadata (description, version, source, licence) | — | `pack` | Update. |
| vocabulary metadata | — | `database` | Keep the database values; record the pack version as `pack_version_seen`. |

- **Pack proposals live in their own table** (`vocabulary_pack_proposal`: vocabulary, code,
  proposed fields, pack version, first and last seen). They are never rows of `vocabulary_term`,
  because a `draft` term is suggested to families (Context). Accepting one creates a change
  request prefilled from it (§4). (Amendment A6.)
- **Codes are reserved** across `vocabulary_term`, open change requests and pack proposals: a code
  in any of them cannot be created by another path.
- **Locking.** The loader and every definer function that writes terms take the same
  transaction-scoped advisory lock (`pg_advisory_xact_lock` on one fixed key), **before** the
  loader reads any term. Without that, the loader can read a term, a publication can commit, and
  the loader's UPDATE then overwrites the published values (a lost update found in PR #35's
  loader). A deploy can therefore never interleave with a publish.
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
**Change types:** create a term, edit labels, aliases, scope, attributes or source, retire (with
an optional successor), reactivate, and adopt or release a vocabulary (§2). **Merge is deferred**
until after the first release (§10, amendment A7).
- Each change request records the term, the term's **base revision**, the proposed values and a
  required reason.
- At most **one open change per term**, enforced by a partial unique index.

**States:** `draft` → `submitted` → `approved` (publishes at once) | `rejected` | `withdrawn` |
`stale`.

**Approval:**
- **A second, different administrator** approves, always. There is no solo mode in this ADR
  (deferred, §7).
- The rule is enforced in the service, in the definer function (§14), and by database
  constraints (amendment A4):
  - `CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_by <> submitted_by))`.
    A bare `approved_by <> submitted_by` is not enough: a NULL passes a CHECK.
  - `submitted_by` is NOT NULL once a change is submitted.
  - The user foreign keys are `ON DELETE RESTRICT`. Accounts are anonymised on closure, never
    deleted, so this never blocks a closure.
- **There is no self-approval path in the interface, the API or the database.**
- With only one administrator, changes can be drafted and submitted but not published. The
  fallback is `masterdata export` and code review (Option A).

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
  - the approval mode (`second_admin` or `loader`; `solo` only if solo mode is ever accepted);
  - the time.
- **Append-only.** A trigger refuses UPDATE and DELETE, as on `audit_event`.
- **The term itself** carries `revision` and `curated`. `replaced_by` (merges, §10) comes with
  the deferred merge change.
- **Backfill.** The migration writes one version row per existing term (revision 1,
  `source = loader`, the current pack version), so every term has a history from day one.
- **Rollback of a term** means proposing a change that restores an earlier version. It is approved
  like any other change. History is never rewritten.

### 6. Audit trail
Every action writes an `audit_event` with `tree_id = NULL`:
- `masterdata.change_submitted`, `…approved`, `…rejected`, `…withdrawn` and `…published`;
- `masterdata.vocabulary_adopted` and `…released`;
- `masterdata.capability_granted` and `…revoked`;
- `masterdata.offer_accepted` and `…declined`;
- `masterdata.loader_conflict`;
- `masterdata.step_up` (a TOTP step-up for the console) and `masterdata.offer_reveal` (§12).

Each definer function writes its own audit row (amendment A3), so an action recorded in the
version history always has an audit event, whatever the service layer does.

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
  - **`platform_capability_grant` is read-only to the application role** (it joins
    `READ_ONLY_TABLES`). Otherwise an injection anywhere in the API could grant the capability to
    itself (amendment A2).
  - The demo seeder never grants it.
  - The CLI refuses an account without a verified email and two-step sign-in.
- **Named accounts only.**
  - One person per account. The grant records the person's name and the reason.
  - Shared or role mailboxes (for example `admin@`, `ops@`, `info@`) are refused by the CLI. They
    are listed in a configurable deny-list.
  - The pilot runbook forbids shared credentials.
- **Two-step sign-in is required, per session** (amendment A5).
  - `user_session` gains `mfa_verified_at` and `mfa_step_up_at`.
  - `mfa_verified_at` is set only when the session was opened with a password plus TOTP. Google
    sessions never set it.
  - A session qualifies only if `mfa_verified_at` is within the last 12 hours **and**
    `mfa_verified_at >= app_user.mfa_enabled_at`. The second test means that turning two-step
    sign-in off and on again (a new secret) disqualifies every older session.
  - Every console write needs `mfa_step_up_at` within the last 15 minutes. It is set by
    `POST /api/v1/auth/step-up {code}`, which shares the login TOTP rate limit and is audited.
  - Turning off two-step sign-in removes console access at once, because it is checked on every
    request rather than cached.
  - Password change and reset must revoke the account's other sessions. The first increment adds
    a test for that, and the fix if it is missing.
- **Server-side authorisation.**
  - Every `/api/v1/admin/master-data/*` route depends on `require_platform(MASTER_DATA_ADMIN)`.
  - A caller without the capability gets **404**, so the console's existence isn't revealed.
  - A holder without a valid second step gets 403 `admin_mfa_required`.
  - Writes need the CSRF header and are rate-limited.
  - The UI only hides controls; the server decides. `UserOut` gains `platform_capabilities`, the
    caller's own capabilities, only to show or hide the console link.
  - **Off by default.** `VSH_MASTERDATA_CONSOLE_ENABLED` defaults to `false`. It is turned on only
    once the go-live checklist records two named administrators (amendment A10).
- **Single-admin installation: no solo mode (deferred).** The owner's position (11 Nov 2026) is
  two named administrators for every publication. Solo mode, its table (`masterdata_solo_mode`),
  its audit events and `approval_mode = solo` are **not** part of this decision.
  - A one-admin installation drafts and submits in the console. Publication waits for a second
    administrator, or the operator exports the change and publishes it by code review (Option A).
  - The earlier design (an operator CLI switch of at most 90 days, a 24-hour wait, a fresh TOTP,
    a permanent banner and a "published without a second reviewer" list) is kept in the
    alternatives below. Adopting it later needs an amendment to this ADR.

### 8. No access to family trees
The capability is a platform permission and grants **no tree permission of any kind**.
- **No tree binding.** Console handlers never bind `app.tree_id`, so row-level security returns
  nothing from tree-scoped tables.
- **No tree code.** Console code may not import tree-scoped models or tree services. A new test
  will check this by parsing the console module's imports; no such test exists yet.
- **The definer functions are the only way across.** They run as the schema owner and RLS is not
  FORCEd, so they see every tree. The offer functions in §12 are therefore cross-tenant by design
  and are hardened as such (amendment A8).
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
  - Refused: control characters, bidirectional overrides, HTML and markup. Reuse `main`'s
    `geo/formats.py` `clean_text`, which already refuses Cc and Cf characters except ZWJ and ZWNJ
    (needed for Indic scripts). PR #35's label check collapsed whitespace only, so RLO and
    zero-width characters passed.
  - Attribute keys come from a fixed list per vocabulary (for example `temple` for kuladevata),
    never free keys.
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
- **Category guard.** The vocabulary key must be one of those §13 marks console-editable: gotra,
  kula, kuladevata, kuladevi, devak and occupation. The allow-list lives in code **and** is
  repeated inside the definer functions. A request naming any other key is refused with 404, so it
  cannot be used to create a list or to adopt a code-controlled one.
- **No automatic checking for prohibited content.** No validator can reliably spot a caste or
  religion category disguised as a gotra. That is what the second administrator is for, and the
  approval screen asks the question explicitly.

### 10. Retirement, merging and stored values
- **Retiring** hides a term from suggestions. Stored references keep resolving, because records
  store the label and the code (ADR-0018 §6). Reactivation is an ordinary change.
- **Merging** (deferred, amendment A7) will retire one term with `replaced_by` pointing at the
  other, so search returns one result. Until then, retirement with an optional successor covers
  duplicates. **Stored family values are never rewritten**, by either: a family that picked the
  retired code keeps its label and code.
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
- **Switching the console off:** `VSH_MASTERDATA_CONSOLE_ENABLED=false` (the default, §7) makes
  every console route answer 404. Published terms stay, and families see no change. `VSH_MASTERDATA_ENABLED=false`
  still turns suggestions off altogether (ADR-0018 §7).
- **Migration downgrade:**
  - It drops the new tables and columns. Every term row and every published value stays in
    `vocabulary_term`.
  - It refuses to run while a change is `submitted`.
  - It refuses to run while any term is `curated`, unless the operator passes
    `-x masterdata_exported=1`. After the downgrade the loader owns every list again and would
    overwrite curated values (the defect in PR #35's downgrade).
  - It restores the application role's write grants.
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

**How the console reads and decides offers** (a later increment, after publication works;
amendment A8):
- The tree-scoped table is read through a `SECURITY DEFINER` function owned by the schema owner.
  Because RLS is not FORCEd, this function can see every tree: it is a cross-tenant read and is
  hardened as one.
  - It takes **no tree id** argument and returns only the columns above, for rows with
    `offer_status = 'offered'`.
  - It is paginated, has a pinned `search_path`, and the application role may only EXECUTE it.
  - Every call is audited.
  - Tests prove it returns no other column or row, and that a non-holder cannot reach it through
    the API.
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
| **Geography (LGD units)** | X | Activated LGD snapshot (ADR-0019) | Read-only. No term edits. Snapshot staging stays in the operator CLI. | — | **No official data is imported until the owner records a licence and attribution review.** Only synthetic fixtures today. Each snapshot will store its own licence and attribution, and the importer will refuse non-fixture files until the review is recorded (geography increment). |
| **Geography aliases** | R (curated) | `geo/aliases.json`, by code review | Read-only (could adopt later by its own ADR) | — | Never a family's spelling. |
| **PIN codes (India Post)** | X | Activated snapshot | Read-only | — | Same licensing gate. A PIN suggests a district and state, never a village or a person's address. |
| **Gotra** | R | `database` once adopted | Create, edit, retire; offers later; merge later | Second admin | No inference: a gotra never implies community, region, religion or pravara (ADR-0026 §3). |
| **Kula / vamsha** | R | `database` once adopted | As gotra | Second admin | |
| **Kuladevata, Kuladevi** | R | `database` once adopted | As gotra, with an optional temple attribute | Second admin | The lists start empty and grow from offers. |
| **Devak** | R | `database` once adopted | As gotra | Second admin | |
| **Pravara (gotra links)** | R (sourced links) | `pack` at first | Read-only at first; later edit with a required source and reviewer | Second admin | A link is suggested only when `reviewed` with a cited source. Never filled in from a gotra. |
| **Occupation** | R | `database` once adopted | Create, edit, retire | Second admin | Fields stay free text. |
| **Honorific** | R | `pack` at first | Read-only | — | Not in the first set; adoption later needs an amendment. |
| **Language** | C (closed list of 23) | `pack` | Read-only | Code review | `allows_custom = false`. Not console-editable, not even labels. |
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
  adopted here. Nor are #35's `religion_community` pack category and its "planned" console card.
  Religion, community and caste remain optional personal fields: no global list, no inference, no
  mandatory value. If wanted, a list needs its own decision under Q4.

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
- **Decision (owner's position, 11 Nov 2026; amendments A2 and A3):**
  - **Read-only to the application role** (all join `READ_ONLY_TABLES`): `vocabulary`,
    `vocabulary_term`, `vocabulary_term_version`, `vocabulary_change_request`,
    `vocabulary_pack_proposal` and `platform_capability_grant`. `tree_vocabulary_term` stays
    writable.
  - **The complete function set**, all `SECURITY DEFINER`, owned by the schema owner:
    - `masterdata_save_draft` (create or edit one's own draft);
    - `masterdata_submit`;
    - `masterdata_withdraw` (author only);
    - `masterdata_reject` (not the author; reason required);
    - `masterdata_approve_publish`;
    - `masterdata_set_authority` (adopt or release; itself an approved change);
    - later, with offers: `masterdata_offer_projection` and `masterdata_decide_offer`.
  - **Each function:**
    - `SET search_path = pg_catalog, public, pg_temp` (`pg_temp` last, so a temporary table or
      function can never shadow a real one); no dynamic SQL;
    - `REVOKE EXECUTE … FROM PUBLIC`, then `GRANT EXECUTE` to the application role only;
    - takes the advisory lock (§3) before it writes a term;
    - writes its own `audit_event` row (`tree_id NULL`).
  - **Checks repeated inside the database:**
    - the approver differs from the author (there is no solo exception);
    - the base revision matches;
    - the vocabulary's authority is `database`;
    - the vocabulary key is on the allow-list (§9);
    - nothing is ever deleted;
    - every published change writes a version row.
  - **A migration test** asserts, for each function: `prosecdef`, the pinned `search_path` in
    `proconfig`, the owner, and that only the application role may EXECUTE it. A second test shows
    that a shadow function in a temporary schema does not change its behaviour.
- **What this buys:** a bug or an injection anywhere else in the API can no longer rewrite, delete
  or truncate the global lists, or skip the version history. Self-approval and deletion are refused
  even if the service layer is wrong.
- **What it does not buy:** the database cannot verify *who* the user is. Someone who fully
  controls the API process can still call the functions with forged user ids. Named accounts,
  per-session two-step sign-in, the audit trail, the version history and `masterdata export`
  before each deploy are the controls for that.
- **What it costs:** the definer functions are themselves attack surface. They stay few and
  small, and each has direct-call negative tests (threats section).
- **The alternative,** a second login role only for the console, adds a credential that sits in
  the same process. It gains little over definer functions and complicates deployment.

## Threats and tests to write before code (threat ID allocated at merge)
Each of these becomes a test in the implementation PRs:
The threat ID is the next free one when the first implementation increment merges (amendment A9).
`main` now holds T63 (#62) and T64 (#71), so draft PR #67 (increment 1) takes T65.

- **Privilege.**
  - A non-holder gets 404 on every console route, parametrised over all routes.
  - A holder without a second-step session gets 403.
  - A session older than 12 hours gets 403.
  - A session opened before two-step sign-in was turned off and on again gets 403.
  - A write with a step-up older than 15 minutes gets 403.
  - A holder whose two-step sign-in was turned off loses access on the next request.
  - A revoked grant loses access on the next request.
  - A Google-only session never qualifies.
  - The application role cannot write `platform_capability_grant` by direct SQL.
  - The grant CLI refuses an unverified email, an account without TOTP, and deny-listed mailboxes.
- **No tree access.**
  - A capability holder gets 404 on every `/trees/{id}` route of a tree they are not in. This
    reuses the parametrised route test.
  - Console handlers never bind a tree.
  - The new import-boundary test passes.
- **Self-approval.** Refused by the service, by the definer function called directly, and by
  the database CHECK, including with a NULL approver.
- **Concurrency.**
  - Two approvals of the same change: exactly one publishes.
  - A stale base revision returns 409.
  - A loader run during a publish is serialised by the advisory lock. The test runs both in two
    connections with a barrier and checks the published values survive.
- **Loader.**
  - Curated terms are never overwritten, retired or re-created, in each row of the §3 table.
  - Pack proposals are never returned by any family-facing `/vocabularies` route.
  - Curated values survive a deploy: publish, run `alembic upgrade head` and `load`, and the value
    is unchanged.
  - CI fails on a conflict in a `pack` vocabulary.
- **Upgrade.** A migration round trip keeps curated, retired and proposed terms. The downgrade is
  refused while a change is submitted, and while a term is curated without the export flag.
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
- **Grants.**
  - The application role cannot INSERT, UPDATE, DELETE or TRUNCATE any table listed in §14.
  - The definer functions refuse self-approval, deletion, a non-allow-listed key and a `pack`
    vocabulary even when called directly.
  - The function attribute test and the `search_path` shadowing test from §14 pass.
- **E2E.** An admin signs in with two-step sign-in, drafts a term, and a second admin approves it.
  A family then sees the suggestion without a deploy, and a family member gets 404 on the console.

The threat model (with the ID allocated at merge) and the privacy model (an "administrators and
global lists" section) are updated in the first implementation PR, not by this proposal.

## Consequences
- **Two migrations, each with a downgrade, chained to `main`'s head at the time** (never to PR
  #35's revisions):
  - **Identity** (first increment): `platform_capability_grant` (read-only to the application
    role), `user_session.mfa_verified_at` and `mfa_step_up_at`. Existing sessions get NULL and so
    do not qualify.
  - **Master data** (third increment), purely additive:
    - `vocabulary.authority` (default `pack`) and `pack_version_seen`;
    - `vocabulary_term.revision` (default 1) and `curated` (default false);
    - `vocabulary_term_version` with its append-only trigger and the backfill (§5);
    - `vocabulary_change_request` and `vocabulary_pack_proposal`;
    - the definer functions and the grant changes (§14).
  - Term rows, codes and labels are not touched, so every stored family reference keeps
    resolving. Adoption of the six lists is an approved change after the deploy, not part of the
    migration.
- **Loader:** it gains the curated rules, the reporting and the history writes.
- **New CLI commands:**
  - `masterdata export`;
  - `masterdata grant` and `revoke`;
  - `load --adopt-pack`.
- **Frontend:** `/admin/master-data`, with lists (showing each list's authority), terms, history,
  the change queue and, later, the offers queue. A 404 shows a not-found page; a 403
  `admin_mfa_required` shows a step-up prompt. It is accessible, works at 390 px (cards instead of
  a wide table) and is marked up for Indic scripts. PR #35's layout, term table, editor, history
  view and diff are adapted; its self-publish queue is not.
- **Operations:**
  - granting the capability and enrolling a second administrator join the go-live checklist;
  - `masterdata export` joins the release runbook.

## Alternatives considered
- **Option A** (the console drafts; a CLI writes packs; code review publishes). It keeps Git as
  the only truth and needs no in-app approval. **Not chosen by the owner**, because every change
  needs a deployment. It remains the fallback for a single-admin installation (§7).
- **Database publication without a second administrator.** Rejected. One compromised or mistaken
  account would change suggestions for every family at once. This includes PR #35's optional
  four-eyes setting, which was off by default.
- **Solo mode** (an operator CLI switch of at most 90 days; solo publication after 24 hours with a
  fresh TOTP and a typed confirmation; a permanent banner; a "published without a second
  reviewer" list that becomes the second admin's first review queue). **Deferred** by the owner on
  11 Nov 2026. It can be reconsidered by amendment.
- **Pack proposals stored as `draft` terms.** Rejected: `draft` terms are suggested to families.
- **Per-session MFA checked only against "MFA is on" for the account** (PR #35). Rejected: a session
  opened before the account enrolled, or before a secret was replaced, would qualify.
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
2. *Can one administrator publish alone?* No. The service, the definer function and a NULL-safe
   CHECK all refuse it, and there is no solo mode (§4, §7, §14).
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
10. *Can a pack proposal reach families before approval?* No. Proposals live in their own table,
    never in `vocabulary_term` (§3).
11. *Can a bug or injection in the API grant itself the console?* No. The grant table is read-only
    to the application role, and only the owner CLI writes it (§7, §14).
12. *Can the offer projection leak another family's data?* It can see every tree, because RLS is not
    FORCEd. It takes no tree id, returns only the reviewed columns of offered rows, and is tested
    and audited as a cross-tenant read (§12).

## Open decisions for the owner
Positions the owner set out on 11 Nov 2026, written into this ADR (accepted as a whole on
12 Nov 2026):
- Solo mode: **deferred**; two named administrators for every publication (§7).
- Offer notes: **never shown** to global reviewers (§12).
- Database privileges: **§14 accepted**, with the read-only list and function set above.
- First vocabularies: **gotra, kula, kuladevata, kuladevi, devak and occupation** (§13).
- Controlled enums, Rashi, Nakshatra and roles stay in code; religion, community and caste get no
  global list (§13).
- LGD and India Post data need a recorded licence and attribution review before any real import
  (§13).

Decided:
1. **Accept this ADR**, as amended: **accepted 12 Nov 2026**.

Still open (none blocks increments 1–3; each default holds until decided):
2. **The offer note.** Also stop collecting it for new offers? That amends ADR-0026 §4.
3. **The two named administrators** for go-live.
4. **Who records the licence review** for real LGD and India Post files.
5. **Geography snapshot approval over HTTP** (PR #35 had one). Recommended: stay on the operator
   CLI; moving it needs its own ADR.

## Implementation plan (each a draft PR from `main`; none merged without the owner's approval)
The consolidation review (PR #64, §8 and §9) gives the reused PR #35 files and the acceptance tests
for each increment.

0. **Before code.** Land PR #60 (CI) on its own (done, 11 Nov 2026). Accept this ADR (done, 12 Nov 2026). Add the "amended by ADR-0028"
   notes to ADR-0006, ADR-0018 and ADR-0026 in a separate change (done, 12 Nov 2026).
1. **Platform capability and sign-in.**
   - `platform_capability_grant` and the grant and revoke CLI.
   - The session MFA columns, the step-up endpoint and `require_platform`.
   - `UserOut.platform_capabilities`.
   - The no-tree-access tests and the import-boundary test.
   - The ADR-0006 note, the threat entry and the privacy-model section.
2. **Read-only console.** Lists (with authority), terms and term detail; the not-found page and
   step-up prompt; the 390 px card layout. Adapted from PR #35's console pages.
3. **Loader, history and database restrictions.**
   - The master-data migration (Consequences) and the version backfill.
   - The loader rules, the advisory lock and the `load --dry-run` CI gate.
   - `export` and `load --adopt-pack`.
   - The read-only grants and the definer functions.
   - The history view.
4. **Second-administrator review and publication.**
   - Draft, submit, approve (second admin, step-up), reject, withdraw and stale.
   - The §9 validator, retirement and reactivation, and rollback by change.
   - Adoption of the six lists.
   - A two-administrator e2e spec.
   - The runbook and go-live checklist updates.
5. **Geography snapshot administration on ADR-0019's infrastructure.**
   - Per-snapshot licence and attribution, and the licence-review gate.
   - PR #35's importer hardening: NUL and empty files refused, a row cap, capped error lists, and
     formula neutralising in the CSV change report.
   - Read-only snapshot status in the console.
6. **Later, each by amendment or its own PR:** offers in the console (§12), merge (§10), and solo
   mode if it is ever accepted.

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

## Amendments of 11 Nov 2026
Made after the consolidation review of PR #35 against this ADR (PR #64,
`docs/architecture/master-data-console-consolidation.md`), and after re-checking `main` at
`5913759`. The status stays **Proposed**.

| # | Amendment | Where |
|---|---|---|
| A1 | Context re-verified at `5913759`: five read-only tables, RLS not FORCEd, all terms `draft` and suggested, licence hard-coded. PR #35's migrations discarded, not re-parented. | Header, Context |
| A2 | `platform_capability_grant` and every new master-data table are read-only to the application role. | §7, §14 |
| A3 | The complete definer-function set, each pinned, locked, audited and attribute-tested. | §6, §14 |
| A4 | NULL-safe approval CHECK, `submitted_by` NOT NULL once submitted, user FKs `ON DELETE RESTRICT`. | §4 |
| A5 | Per-session MFA: `mfa_verified_at` compared with `mfa_enabled_at`, a 15-minute step-up column and endpoint, password change revokes other sessions. | §7 |
| A6 | Pack proposals live in `vocabulary_pack_proposal`, never as `draft` terms; codes reserved across terms, requests and proposals; advisory lock taken before the loader reads. | §3 |
| A7 | Merge and `replaced_by` deferred; retirement with a successor covers the first release. | §4, §5, §10 |
| A8 | The offer projection is treated as a cross-tenant read: no tree id, fixed columns, audited, tested; offers come in a later increment. | §8, §12 |
| A9 | The threat ID is allocated at merge (T63 and T64 are taken on `main`; increment 1 takes T65). | Threats |
| A10 | `VSH_MASTERDATA_CONSOLE_ENABLED` defaults to `false` until two named administrators are recorded. | §7, §11 |
| — | The owner's positions of 11 Nov 2026: solo mode deferred; offer notes hidden; §14 accepted; the six first vocabularies; honorific, pravara and language stay `pack`; no religion, community or caste lists; geography licence review before real data. | §7, §12, §13, §14, Open decisions |

**Re-checked 11 Nov 2026 at `3cb12f9`** (integration audit): `main` changed only in the agent
ticket factory, CI and an overload test since `5913759`, so the Context still holds. The single
Alembic head on `main` is `d9b4f2c6a713`. PR #62 still holds T63. Draft PR #67 (increment 1) uses
T64 and adds migration `e7c2a9f4b310`, which revises `d9b4f2c6a713` like #62's `f2a9c4e7d815`:
whichever merges second must re-parent its migration onto the other so `main` keeps one head.
The status stays **Proposed**.

**Re-checked 12 Nov 2026 at `b8c248b`**: since `3cb12f9`, `main` merged #60 (CI apt hardening),
#62 (tradition ownership guard, T63, migration `f2a9c4e7d815`), #71 (record downgrade guard, T64,
migration `a4d7e2c9b153`), the ticket factory upgrade (#68, #69, #72) and #73. None touches master
data, `READ_ONLY_TABLES`, RLS forcing or the licence, so the Context still holds. The single
Alembic head on `main` is `a4d7e2c9b153`. Draft PR #67 (increment 1) has been re-parented onto it
(`e7c2a9f4b310`, one head) and uses threat ID T65. The status stays **Proposed**.

**Accepted 12 Nov 2026** by the owner, as amended (A1–A10 and the 11 Nov positions). Open decisions
2–5 stay open with the defaults above: offer notes are still collected but never shown to
reviewers; the console stays off (`VSH_MASTERDATA_CONSOLE_ENABLED=false`) until two named
administrators are recorded; no real LGD or India Post data is imported before a recorded licence
review; geography snapshot approval stays on the operator CLI.
