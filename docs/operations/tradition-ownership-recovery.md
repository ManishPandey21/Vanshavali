# Tradition ownership: rollout, rollback and recovery (PR #51 follow-up)

Status: **proposal for review.** Nothing here has been run against pilot or production data.
Scope: family traditions after migration `8d2e6b4f1a37` (PR #51, ADR-0027 increment 2) and the
follow-up migration `f2a9c4e7d815`, and the downgrade guard `a4d7e2c9b153` for documents, photo
collections and takedown (the same downgrade shape; section 2).

## 1. What the follow-up changes

| Change | Where | Effect on access |
|---|---|---|
| Leftover tradition `PRIVATE_SELF` rows become `ONLY_ME` | `f2a9c4e7d815` upgrade | Narrows: the tree OWNER loses a view the evaluator gave them by mistake |
| Trigger `tradition_entry_record_owner`: `PRIVATE_SELF` is stored as `ONLY_ME`; an INSERT without an owner gets the author's current membership | `f2a9c4e7d815`, `app/models/culture.py` | Older code (after `rollback.sh`) can no longer create entries the tree owner reads or that nobody owns; existing owners are never changed |
| A downgrade that would run `8d2e6b4f1a37`'s downgrade is refused while it would widen or discard access | `f2a9c4e7d815` downgrade | None (it refuses, atomically) |
| A downgrade that would run `d9b4f2c6a713`'s (takedown), `b5c1e7a93d42`'s (collections) or `3f6a8c1d2e94`'s (documents) downgrade is refused while it would widen or discard access | `a4d7e2c9b153` downgrade, `app/core/downgrade_guard.py` (shared with `f2a9c4e7d815`) | None (it refuses, atomically) |
| An ownership offer cannot be accepted, and is not listed, once the owner has left | `ownership.service.accept`, `offers_for_me` | Closes a claim of an orphan |
| Only me is refused on a record without an owner (`orphan_only_me`) | `sharing.core.refuse_unreadable` | Stops an admin making an orphan unreadable by everyone |

## 2. Migration and rollback matrix

"Old code" is the release before #51 (`rollback.sh` runs it on the newer schema; the
release runbook calls this the normal rollback).

| Step | Data effect | Access effect | Reversible? |
|---|---|---|---|
| Upgrade to `8d2e6b4f1a37` (already merged) | Adds owner (backfilled from `created_by` where a membership exists); `PRIVATE_SELF` → `ONLY_ME` | Same readers at migration time. Authors removed and re-invited **before** the upgrade are backfilled as owners through their *new* membership (see decision D2) | Not in effect |
| Upgrade to `f2a9c4e7d815` | Leftover `PRIVATE_SELF` → `ONLY_ME`; trigger installed | Narrowing only | Trigger yes; narrowing is kept on downgrade |
| Upgrade to `a4d7e2c9b153` | None (no schema change) | None | Yes |
| Re-run upgrade (retry after failure) | Idempotent (`UPDATE … WHERE`, `CREATE OR REPLACE`, `DROP TRIGGER IF EXISTS`); one transaction | None | — |
| Downgrade to `f2a9c4e7d815` | None | None | Yes, re-upgrade |
| Downgrade below `d9b4f2c6a713` (takedown) with an active suspension or a record marked suspended | **Refused before any change** (`a4d7e2c9b153`, counts only) | None; otherwise every suspended document, tradition and collection would become readable again and reports and suspensions would be dropped | — |
| Downgrade below `b5c1e7a93d42` (collections) with any collection or collection grant | **Refused before any change** (`a4d7e2c9b153`) | None; otherwise collections, their items and grants would be deleted | — |
| Downgrade below `3f6a8c1d2e94` (documents) with any of: Only me, Selected members, Selected branch or download-off documents, document grants, an owner who is not the author, an orphan whose author is a member again | **Refused before any change** (`a4d7e2c9b153`) | None; otherwise Only me → `PRIVATE_SELF` (tree OWNER reads), Selected members → `CUSTOM` (admins read), branch audience and download switch dropped, transfers forgotten | — |
| Downgrade to `d9b4f2c6a713` / `c7e3a1f5b829` / `7b2e4d9a1c63` / `e4b8c2d6f913` / `b5c1e7a93d42` / `8d2e6b4f1a37` | Drops the trigger (and takedown reports / narrowing notices / the family calendar / pending offers / collections per those migrations) | Pending offers are lost (they give no access). Takedown, notices, calendar and collections: see their migrations | Yes, re-upgrade |
| Downgrade below `8d2e6b4f1a37` with any of: tradition grants, Selected members entries, orphaned Only me entries, an orphan whose author is a member again, an owner who is not the author | **Refused before any change** (RuntimeError, counts only) | None | — |
| Downgrade below `8d2e6b4f1a37` with none of those | Owners dropped; `ONLY_ME` → `PRIVATE_SELF` | Unchanged: every Only me entry is owned by its own author's membership, which old code matches by user id | Re-upgrade restores owners (same memberships) |
| Downgrade with a relative target (`-1`), `base`, a branch-qualified target or offline `--sql` | Both guards evaluate as if they reach every guarded revision (fail closed; `--sql` refuses outright) | — | Use an explicit revision id, online |
| Downgrade that stops exactly at a guarded revision (e.g. `alembic downgrade 8d2e6b4f1a37`) | That revision's own downgrade does not run, so it is not checked | — | — |
| Application rollback to pre-#51 code, schema kept | Old code cannot load `ONLY_ME` / `SELECTED_MEMBERS` (validated enum): traditions list, export and search fail with 500 in trees that have such entries. Its writes are made safe by the trigger | Fail-closed (no leak), loss of availability for traditions | Roll forward |
| Orphan handling | No automatic reassignment, no admin access; grantees keep reading; inventory counts only | Unchanged | — |

## 3. Rollout checklist (staging first, then pilot)

1. [ ] Review and approve this PR, including decisions D1–D5 below (or explicitly defer them).
2. [ ] Confirm the release notes say: application rollback below #51 makes traditions unavailable
       (fail-closed) in trees with private entries; roll forward instead.
3. [ ] Staging: `deploy.sh <sha>` (pre-deploy backup runs; migrations: `… → 7b2e4d9a1c63 → c7e3a1f5b829 → d9b4f2c6a713 → f2a9c4e7d815 → a4d7e2c9b153`).
4. [ ] Staging: `SELECT count(*) FROM pg_trigger WHERE tgname = 'tradition_entry_record_owner'` = 1.
5. [ ] Staging: run the inventory (section 5) **read-only** with the owner's approval; record the
       counts only. Expect `legacy_private_self` = 0.
6. [ ] Staging: smoke test plus: create Only me tradition as a contributor → tree owner gets 404;
       offer it, remove the author, offeree gets 404 on accept.
7. [ ] Staging drill (optional, disposable database only): `alembic downgrade 3f6a8c1d2e94` on a
       restored copy with a Selected members entry → refused, version unchanged.
8. [ ] Pilot: same steps 3–6, in the announced window.
9. [ ] Watch `HighServerErrorRate` for 30 min; a 500 on `/traditions` after a rollback means old code
       is running: roll forward.

## 4. Recovery procedures

**4.1 A downgrade below `8d2e6b4f1a37`, `3f6a8c1d2e94`, `b5c1e7a93d42` or `d9b4f2c6a713` is refused.**
The same applies to all of them; never lift a suspension or delete a collection just to get past the guard. Do not edit data to get past the guard.
Choose with the owner:
- *Roll forward* (preferred): fix the problem in a new migration.
- *Restore the pre-deploy backup* into a new database (`backup-restore-runbook.md`), accepting the
  loss of writes since it, or PITR to just before the migration. This needs the owner and a pilot
  announcement (release runbook).
- A reviewed, written data procedure that converts each affected entry *with its owner's consent*
  (e.g. owners narrow Selected members to Only me) is possible but is a product decision (D4).

**4.2 Application rollback below #51 happened.** Traditions in trees with private entries answer 500
(fail-closed). Roll forward as soon as possible. Entries written meanwhile by old code are stored
as `ONLY_ME` / owned by the author's current membership (trigger). After rolling forward, run the
inventory; `legacy_private_self` must be 0.

**4.3 Someone asks for their old private entries back after being removed and re-invited.** There
is no supported recovery today (ADR-0027 §2: admins cannot claim orphans; re-invitation gives
nothing back). Do not reassign by user id, e-mail or name. Record the request; see D1.

**4.4 An orphan with a pending offer.** The offer has lapsed: it cannot be accepted and is not listed.
The member it was made to can still decline it (clears the column). No operator action.

## 5. Read-only inventory

`docs/operations/tradition-ownership-inventory.sql`: categories × privacy level × count. No ids,
titles, bodies, names or addresses. Run as the schema owner (row-level security would otherwise
hide rows), inside `BEGIN READ ONLY … ROLLBACK`, only with the owner's approval. It is tested on a
disposable database (`test_tradition_ownership_recovery.py::test_the_read_only_inventory_returns_counts_only`)
and **has not been run anywhere else**. Deciding what to do about any category is D1–D3.

## 6. Decisions that stay with the owner

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Recovery for an author removed and re-invited | (a) none, retention only (ADR-0027 §2 today); (b) *pre-departure* only: the owner transfers, or marks entries "keep for me if I return", before leaving; (c) author self-recovery: same account, recent re-authentication, within a window, entry still orphaned, audited, the content never shown to admins; (d) admin-approved re-link without reading | **(a) now, (b) next.** (c) needs a legal view on whether a removal (e.g. for abuse or a compromised account) should block it; (d) is an admin override and is not proposed |
| D2 | Entries backfilled by `8d2e6b4f1a37` to an author re-invited *before* the upgrade (`owner_membership_newer_than_entry`) | (a) keep: they had access by user id before #51; (b) orphan them in a forward migration (narrows their own access) | **(a)**, unless the inventory shows a case that came from a removal for cause |
| D3 | Ownerless entries written by old code before `f2a9c4e7d815` (`orphaned` rows whose author's *same* membership still exists and predates the entry) | (a) leave as orphans; (b) a reviewed forward migration assigns them to that membership, excluding any entry with a `record.ownership_transferred` event | **(a)** unless the inventory finds any; then (b) as its own PR |
| D4 | Downgrade below `8d2e6b4f1a37` (or `3f6a8c1d2e94`, `b5c1e7a93d42`, `d9b4f2c6a713`: `a4d7e2c9b153`) when it would change access | (a) refused, no override (this PR and `a4d7e2c9b153`); (b) an operator override with a recorded approval | **(a)**: restore from backup is the reviewed path |
| D5 | Grant revival and stale authorisation | Grants are per membership (cascade) and the grant cache is per request; no change proposed | Keep |

## 7. Limits that code cannot close

- Content already read, copied or exported before a removal cannot be recalled (ADR-0027 §7).
- The guard protects downgrades that start at or above `f2a9c4e7d815`; a database still below it is
  protected only by reading `8d2e6b4f1a37`'s docstring.
- A forced manual downgrade (editing `alembic_version`, hand-run SQL) bypasses every guard.
- Old code cannot be changed: its 500s on new levels after an application rollback remain.
- The guards protect downgrades that start at or above `a4d7e2c9b153` (documents, collections,
  takedown) and `f2a9c4e7d815` (traditions). A database still below them is protected only by the
  docstrings of `3f6a8c1d2e94`, `b5c1e7a93d42`, `d9b4f2c6a713` and `8d2e6b4f1a37`.
- The takedown downgrade also drops open reports and the history of lifted suspensions. They give
  no access, so they are not counted; take a backup first if they matter.
- Any document grant blocks the documents downgrade, even on a `CUSTOM` document that the older
  code reads the same way (fail closed; restore from backup instead).
- Documents written by pre-ADR-0027 code after an application rollback are ownerless (no trigger
  like `tradition_entry_record_owner` exists for documents). Still open.
