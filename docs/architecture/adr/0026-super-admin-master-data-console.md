# ADR-0026: Super Admin master-data console

- Status: Accepted · Date: 2026-11-05
- Relates to: ADR-0006 (authorisation; SYSTEM_ADMIN has no tree access), ADR-0018 (vocabularies),
  ADR-0019 (geography, proposed), ADR-0005 (sessions, CSRF), threat T12, T41, T44
- Plan: [india-master-data-and-smart-forms-plan.md](../india-master-data-and-smart-forms-plan.md),
  phase A ("admin curation endpoints") and the Super Admin console request of 5 Nov 2026

## Context
ADR-0018 shipped the global vocabularies (gotra, kula, kuladevata, kuladevi, occupation, honorific,
language) as JSON packs loaded by a CLI. Changing a label, adding a gotra or retiring a duplicate
therefore needs a code change and a deployment. ADR-0018 §3 deferred "promoting into the global
vocabulary" to a later admin action, and the plan lists "admin curation endpoints" in phase A.

The platform already has `app_user.is_system_admin`, but nothing reads it: ADR-0006 §6 gives a
system admin "platform endpoints only, no implicit tree access" (T12). The owner asked for a Super
Admin console that maintains global master data from the browser, without opening family trees.

Two things must not happen:
1. curating global data becomes a way to read family records, or
2. the console becomes a way to turn controlled system values (roles, privacy levels, relationship
   types, review states, the astronomical sets) into editable data.

## Decision

### 1. A narrow platform capability, separate from tree permissions
- `app/authz/platform.py` defines `PlatformCapability.MASTER_DATA_ADMIN`. It is held by active
  accounts with `is_system_admin`. Deny by default: no other capability exists yet.
- The capability is checked by one dependency, `MasterDataAdmin`, on every handler under
  `/api/v1/admin/master-data/*`. Accounts without it get **404** (the surface is not advertised).
- It is **not** a tree `Permission` and `TreeContext` never consults it. A system admin still gets
  404 on every `/trees/{t}/…` route unless they are an ordinary member of that tree.
- The admin module (`masterdata/admin.py`) reads and writes only `vocabulary`, `vocabulary_term`
  and `vocabulary_change`. It never queries `tree_vocabulary_term` or any tree-scoped table, so no
  family entry appears in the console's lists, counts, search or duplicate checks.

### 2. Two-step sign-in is mandatory for the console
A global term is shown to every family. A stolen password alone must not be enough to change it.
Every console request (reads included, so the surface is consistent) needs `mfa_enabled_at`;
otherwise **403 `admin_mfa_required`**, and the UI sends the admin to Account → two-step sign-in.
The existing session controls apply unchanged: cookie session, idle/absolute expiry, CSRF
double-submit on every write, forced password change first (`current_user`).

Step-up re-authentication per action was considered and deferred: the actions are reversible
(nothing is deleted, see §5), every one is audited, and four-eyes publication (§3) is available.

### 3. Every edit is a change request; publication applies it
- New table `vocabulary_change`: vocabulary, term code, `action` (create / update / retire /
  reactivate), `status` (pending / published / rejected / withdrawn), `base_revision`,
  `previous` (snapshot of the term when proposed), `proposed` (the complete editable field set
  afterwards), `reason` (required), `source_reference`, proposer, decider, times, decision note.
- An admin either **saves a draft** (pending) or **publishes at once**. Pending changes are listed
  under "Pending reviews"; another admin, or the proposer, publishes or rejects (with a note); only
  the proposer can withdraw. A decided change can never be decided again.
- **One open change per term** (409 `change_pending`), so reviewers never see competing drafts.
- **Four-eyes** is a setting, `VSH_MASTERDATA_REQUIRE_SECOND_ADMIN` (default off for the
  single-admin pilot). When on, the proposer cannot publish their own change (403
  `second_admin_required`). ADR-0019 requires it for activating an official geography snapshot.
- The published rows of `vocabulary_change` are the permanent **change history** of each term
  (previous value, proposed value, who, when, why, source, decision).

### 4. Optimistic concurrency, and packs that never overwrite the console
- `vocabulary_term.revision` starts at 1 and increases on every applied change (console or pack).
  A change carries the revision the editor saw. Proposing against an older revision is refused
  with 409 `stale_revision`; publishing a draft whose term moved on is refused with 409
  `stale_change` (and the draft is flagged `stale` in the list). No lost updates.
- `vocabulary_term.managed_by` is `pack` or `admin`. Publishing any console change makes the term
  `admin`. The pack loader **never** changes or retires an `admin` term; its report counts them as
  `kept` (`= key:code (curated in the console, kept)`), so an operator sees where a pack and the
  console disagree. Pack terms the console never touched keep loading as before (ADR-0018 §4).
- `vocabulary_term` also gains `successor_code`, `created_by` and `updated_by`.

### 5. Retirement, never deletion
There is no delete. **Retire** hides a term from suggestions (`GET /vocabularies/{key}` excludes
it unless `include_retired=true`) and may name a `successor_code` (an existing active term in the
same list). Stored family values keep the label as typed (ADR-0018 §6) and the code reference stays
valid, so nothing becomes unreadable. **Reactivate** brings a retired term back as draft or
reviewed. Editing a retired term is refused until it is reactivated.

### 6. What the console may edit, and what it may not
- Only rows of `vocabulary` are listed. Controlled values are code (`enums.py`,
  `astrology/vocab.py`, `smartadd/terms.py`) and have no rows, so they cannot be reached
  (404). Religion, community and jati have no vocabulary (ADR-0018 §2); a proposed, opt-in design
  is in the ADR-0018 amendment and is **not** implemented.
- Vocabulary metadata (`allows_custom`, `fixed_membership`, `category`, source, licence) stays
  pack- and ADR-controlled. The console edits terms only.
- `vocabulary.fixed_membership` marks closed sets (now: `language`; later the astronomical sets if
  they move into vocabularies). Their labels, translations and aliases can be corrected, but terms
  cannot be created, retired or reactivated (422 `fixed_vocabulary`). A 13th rashi or a 28th
  standard nakshatra is therefore impossible through the console.
- `vocabulary.category` groups lists in the console (heritage, languages_terminology, other; later
  geography, astrology, religion_community).

### 7. Validation
Input models forbid unknown fields (no mass assignment of `managed_by`, `revision`, authorship…).
Codes `^[a-z0-9][a-z0-9_]{0,79}$` and never change after creation; English and Hindi labels
required, at most 12 language-tagged labels of ≤ 200 characters; ≤ 30 aliases; scope slugs;
attributes ≤ 20 flat values; `source_url` only `http(s)://` (no `javascript:`/`data:`); parent and
successor must be active terms of the same list and not the term itself; reason 3–2000 characters.
**Duplicates**: a new or edited label/alias that is the same word in another spelling or script
(`match.same_value`, retired terms included) is refused with 409 `possible_duplicate` and the
matches, unless the admin confirms `allow_similar`; an existing code is always 409 `code_taken`.
A live check (`POST …/duplicates`, writes nothing) warns while typing. Labels are stored and
returned as data and rendered as text (React escaping).

### 8. Publication reaches users without a deployment
Publishing bumps `vocabulary.revision`, which `GET /vocabularies` now returns. The SPA caches
suggestions for at most five minutes (TanStack Query `staleTime`, refetch on focus), so a published
term reaches every user within that time; the publishing browser refreshes at once. Stored values
are never rewritten by a publication.

### 9. Audit
Each proposal and decision writes `masterdata.change_proposed / _published / _rejected /
_withdrawn` with `tree_id = NULL`, `target_type = vocabulary_change` and details holding only the
vocabulary key, term code and action. The values themselves are public reference data and live in
`vocabulary_change`. No family value is ever logged.

### 10. API (`/api/v1/admin/master-data`, OpenAPI tag `master-data-admin`)
| Method | Path | Purpose |
|---|---|---|
| GET | `/vocabularies` | lists with counts per status and pending changes |
| GET | `/vocabularies/{key}/terms?q=&status=&managed_by=&sort=&cursor=&limit=` | terms, retired included, any-script search, cursor pagination |
| GET | `/vocabularies/{key}/terms/{code}` | one term with its change history |
| POST | `/vocabularies/{key}/duplicates` | duplicate check, writes nothing |
| POST | `/vocabularies/{key}/changes` | propose create / update / retire / reactivate; `publish: true` applies at once |
| GET | `/changes?status=&vocabulary=&cursor=` | pending reviews and change history |
| GET | `/changes/{id}` | one change (with `stale`) |
| POST | `/changes/{id}/publish` · `/reject` · `/withdraw` | decide |

### 11. Rollback
- `VSH_MASTERDATA_ENABLED=false` answers 404 on the console too (as on the user endpoints).
- Migration `7d4a2c9e1b60` has a downgrade. It drops `vocabulary_change` (the history) and the new
  columns. Terms keep their current labels but become pack-managed again, so the next pack load can
  overwrite console edits: export the history first (`pg_dump -t vocabulary_change`) if it matters.

## Consequences
- The pilot's seeded system admin must turn on MFA before using the console. Provisioning named
  admins on staging/pilot is still out of scope and needs its own ADR (`docs/operations/dev-accounts.md`).
- Search in the console is in memory per vocabulary, like ADR-0018 (fine below a few thousand
  terms). Geography (ADR-0019) has its own tables and database search.
- Usage counts per term ("which records would a retirement affect") need a privacy-safe aggregate
  across trees (RLS). Deferred: the console shows nothing about family usage today.
- Promotion of a family's own entry into a global list (ADR-0018 §3) stays out of scope. It will be
  a submission that the family explicitly sends, sanitised (label and aliases only, no tree,
  person or user identifiers), and lands as a pending `vocabulary_change`; never automatic.

## Stress test (grill-me)
- *Can a system admin read a family's kuladevata through the console?* No: the module never
  queries tree tables; `test_system_admin_still_has_no_tree_access` checks lists, counts, search
  and duplicate checks, and tree routes stay 404.
- *Can a tree OWNER or FAMILY_ADMIN reach the console by calling the API?* No: 404 on every
  endpoint (`test_ordinary_users_cannot_reach_the_console`, parametrised over all of them).
- *Two admins edit the same term.* The second gets 409 `stale_revision`; a stale draft cannot be
  published (`test_edits_are_refused_when_someone_else_changed_the_term`, `…draft_goes_stale…`).
- *A release ships an updated pack after an admin fixed a label.* The loader keeps the admin's
  version and reports it (`test_pack_loader_never_overwrites_console_curation`).
- *An admin retires a gotra that families stored.* Values stay readable and references valid
  (`test_retired_terms_keep_stored_values_readable`).
- *Stored XSS through a label or source link.* Labels are text; links are `http(s)` only
  (`test_malicious_or_malformed_changes_are_refused`).
- *A compromised admin password.* MFA is required; every action is audited; nothing is deleted.

## Alternatives considered
- **Reuse tree roles (e.g. a "platform" tree).** Rejected: mixes platform and family authority and
  invites "admin sees everything" shortcuts.
- **Direct CRUD without change requests.** Rejected: no review step, no history of previous values,
  lost updates between admins.
- **Edit the JSON packs from the UI (write to the repository).** Rejected: needs a deployment, and
  the server must never write its own code.
- **Let the console edit every enum.** Rejected by ADR-0018 §1: system states with behaviour stay code.
