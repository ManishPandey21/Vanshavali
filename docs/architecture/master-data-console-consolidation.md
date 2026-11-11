# Master-data console consolidation review: PR #35 vs PR #61 (ADR-0028)

- Date: 11 Nov 2026. Analysis only. Nothing was merged, closed, deployed or force-pushed.
- Verified against `main` at `5913759` (merge of #63). Every finding below cites code on that
  commit or on the PR heads listed in §1.
- Recommendation in one line: **adopt ADR-0028 (PR #61) as the canonical design, with the
  amendments in §6. Do not merge or rebase #35. Port a small, named set of its code (§3) into five
  new increments (§8), each built on `main`.**

## 1. Verified state

| Item | Value |
|---|---|
| `main` | `5913759`. Alembic: one head, `d9b4f2c6a713` (one past merge revision, `f0a1b2c3d4e5`). CI for `2da39a9` green; `5913759` was running at the time of writing. |
| PR #35 `claude/dreamy-rubin-yqdy2k` | Head `dc7b617`, base `c86c203`, **113 commits behind `main` at `5913759`** (124 at `3cb12f9`), `mergeable_state: dirty`. 80 files, +16 845/−4 880. No CI on the head; last green run was `e315e71` (7 Nov). |
| PR #61 `claude/confident-ptolemy-hzgaey` | Head at review time `c0787e9` (604 lines); amended on 11 Nov with A1–A10 (`178c474`, 769 lines) and since merged with `main`. **Docs only**: `adr/0028-…md` and an index row. |
| PR #60 `claude/ci-apt-hardening` | Commits `b103fef`, `331a83a` (branch since merged with `main` and hardened). **Patch-identical** (`git patch-id --stable`) to #35's `94661b3` and `dc7b617`. |
| PR #62 `claude/tradition-ownership-…` | Head `b7193b7`, 7 behind. Migration `f2a9c4e7d815` → `d9b4f2c6a713` (one head). Claims threat **T63**. Does not touch master data. CI green. |
| PR #19 (draft, Oct) | An older "vocabularies in the database (ADR-0019)" proposal. It is superseded by ADR-0018 and ADR-0019 on `main` and is out of scope here. |
| Master data on `main` | Nine JSON packs. Every live term is `draft` (85 terms: gotra 16, kula 7, occupation 17, honorific 8, language 23, pravara 14; devak, kuladevata and kuladevi are empty). The loader (`masterdata/loader.py`) is the only writer and runs as the schema owner. Offers are decided by an operator CLI (`masterdata/curation.py`) that writes pack JSON, so changes go through code review (ADR-0026 §4). |
| Grants on `main` | `vanshavali_app` has full DML on everything except `READ_ONLY_TABLES` = `geo_snapshot`, `geo_unit`, `geo_unit_alias`, `pincode_office`, **`panchang_day`** (`models/rls.py:102`). ADR-0028 says "four geography tables"; that text is stale. RLS policies are **not FORCEd** (`rls.py:9`), so the schema owner bypasses them. |
| Identity on `main` | `app_user.is_system_admin` is a single flag (seeded for `superadmin@example.com` in dev/test). TOTP is account-level (`mfa_enabled_at`). `user_session` has **no** MFA column. `UserOut` (the `/me` response) does not expose `is_system_admin`. |
| ADR numbers on `main` | 0026 = cultural depth (accepted), 0027 = record sharing, 0029 = agent factory. 0028 is free and reserved by #61. |
| Threat IDs on `main` | T44 = geography, T45 = change proposals, max = T62. #62 takes T63. |

**Trial merge** of #35 into `main` (throwaway worktree, aborted): 30 conflicted files, 12 of them
add/add (`modules/geo/*`, `models/geo.py`, `cli/geo.py`, `test_geo.py`, `PlaceCascade.tsx`…).
Merging would also leave **two Alembic heads** (`9e3b5d7f2a14`, `d9b4f2c6a713`), and both
geography migrations create `geo_snapshot`, `geo_unit`, `ix_geo_unit_code`, `place.lgd_level` and
`ck_place_place_lgd_level`. So `upgrade head` would fail with a duplicate object even after a merge
revision.

## 2. PR #35 vs PR #61, by concern

PR #61 is a design. PR #35 is working code for an older design. The columns compare #35's code
with what ADR-0028 specifies.

| # | Concern | PR #35 (code) | PR #61 / ADR-0028 (design) | Verdict |
|---|---|---|---|---|
| 1 | Super Admin authz and MFA | `authz/platform.py`: capability = `is_system_admin`. Non-holder → 404; no MFA → 403 `admin_mfa_required`. MFA check is **account-level** (`user.mfa_enabled_at`); no session check, no step-up. | Separate grant; `user_session.mfa_verified_at` ≤ 12 h; TOTP step-up ≤ 15 min for approve and publish; 404 / 403 split as in #35. | **Adapt** #35's `require_platform` shape and its 404/403 contract. **Replace** the source of the capability and the MFA test. |
| 2 | Explicit platform capability | None. Every system admin is implicitly a master-data admin. | `platform_capability_grant`, granted and revoked by owner CLI only, audited, named accounts, deny-list of role mailboxes. | **Replace** (ADR-0028). |
| 3 | Vocabulary create/edit/retire/reactivate | Implemented (`masterdata/admin.py`) for every vocabulary in the DB. Language labels are editable; closed sets are guarded by `fixed_membership`. | Only vocabularies with `authority = database`, and only those on a code allow-list. Adds merge. | **Adapt** the service logic (`_validate`, `_check_reference`, `find_similar`, retire successor). **Defer** merge. |
| 4 | Change requests and second admin | `vocabulary_change` (pending/published/rejected/withdrawn). Four-eyes is **optional and off by default** (`masterdata_require_second_admin: bool = False`, `config.py:145`). `publish=true` on create publishes at once. UI Publish button shown on one's own change (`MasterDataPages.tsx:419`). | Mandatory second admin: service check, DB `CHECK (approved_by <> submitted_by)`, definer function. States draft → submitted → approved/rejected/withdrawn/stale. | **Replace** the policy. **Adapt** the table shape and the pending-queue UI. |
| 5 | Loader and source of truth | Per-term `managed_by = pack/admin`. Loader skips `admin` terms. No lock. | Per-vocabulary `authority`; `curated` per term; full rule table (§3); advisory lock shared with publication; history rows for loader writes; CI fails on conflicts in pack vocabularies; `export`. | **Replace** with ADR-0028 §3. #35's "kept" report line is a useful idea to keep. |
| 6 | Concurrency and history | `revision` on terms and vocabularies; `base_revision` → 409 `stale_revision`/`stale_change`; one open change per term (partial unique index); history = the mutable change table. | Same concurrency, plus append-only `vocabulary_term_version` (trigger refuses UPDATE/DELETE). | **Reuse** the concurrency logic and partial index. **Replace** the history store. |
| 7 | DB grants and definer functions | None. App role keeps full DML on vocabulary tables and on its own history. | Vocabulary tables read-only to the app role; publication only through `SECURITY DEFINER` functions with a pinned `search_path`. | **ADR-0028 with amendments** (§6 A2–A4). |
| 8 | Global audit and family isolation | Audit events carry vocabulary, code and action only, with no tree. Test `test_system_admin_still_has_no_tree_access`. Service imports only global models. | Same, plus import-boundary test, no `bind_tree`, offer projection via definer function without tree, offerer, time or note. | **Reuse** #35's audit helper and test idea. **Add** the boundary test. |
| 9 | UI, accessibility, Hindi | `/admin/master-data`: dashboard, term table, editor with live duplicate check, lifecycle dialog, history, pending queue. Strong basics (`aria-describedby`/`aria-invalid`, captions, live regions, `lang` on Hindi inputs, en/hi parity). Gaps: §4 F9. | Lists, terms, history, change queue, offers queue, 390 px, Indic markup. | **Adapt** (per-file list in §3). |
| 10 | Geography | Second, incompatible implementation: per-snapshot copies, 9 levels, HTTP four-eyes snapshot admin. | Geography read-only in the console; snapshots stay with the ADR-0019 operator CLI; licensing gate. | **Already in `main`** (ADR-0019, `8e4a1f6c2b37`). Port only importer hardening and per-snapshot licence fields (§3). |
| 11 | Migrations and rollback | `7d4a2c9e1b60` and `9e3b5d7f2a14` fork from `5c2d8e1f7a90`. The `7d4a…` downgrade turns curated terms back into pack terms, so **the next load overwrites them**. | One new migration on `main`'s head. The downgrade keeps term rows, refuses while a change is submitted, and requires `export` first. | **Discard both #35 migrations** (§5). |
| 12 | Tests and performance | 41 backend (`test_masterdata_admin.py`), 5 Vitest, 1 e2e (single admin self-publishes). `list_terms` filters in Python with offset cursors (fine at ≤ a few hundred terms per list). | Test list in "Threats and tests"; no performance numbers. | **Adapt** 15 of the 20 test functions, rewrite 2 and delete 1 (§3). Add the ADR-0028 negatives (§9). |

## 3. Feature-reuse matrix (exact files)

Paths are in PR #35 unless they start with `main:`.

### Backend

| File | Verdict | Justification |
|---|---|---|
| `backend/app/authz/platform.py` | **Adapt** | Keep `PlatformCapability`, deny-by-default and the 404/403 split. Replace `capabilities()` (reads `is_system_admin`) with a lookup in `platform_capability_grant` (`revoked_at IS NULL`). Replace the `mfa_enabled_at` test with the session check (§6 A5). |
| `backend/app/api/deps.py` (`AdminContext`, `master_data_admin`) | **Adapt** | Good shape: no tree in the context. Add the console flag (`VSH_MASTERDATA_CONSOLE_ENABLED`), the session lookup and a rate limit. |
| `backend/app/core/config.py` (`masterdata_require_second_admin`) | **Discard** | ADR-0028 makes the second admin mandatory. A switch is the vulnerability (F1). |
| `backend/app/models/masterdata.py` (`VocabularyChange`, term `revision`/`managed_by`/`successor_code`/`created_by`/`updated_by`, vocab `category`/`fixed_membership`/`revision`) | **Adapt (partial)** | Keep: term `revision`, the change-request table shape (rename to `vocabulary_change_request`, states per ADR-0028, `approved_by` NOT NULL when approved), and the partial unique index. Replace `managed_by` with `vocabulary.authority` plus `vocabulary_term.curated`. `successor_code` becomes `replaced_by` (merge, deferred). Drop `category`; derive console grouping in the frontend from the allow-list. Drop `fixed_membership`; closed lists stay `pack`. |
| `backend/app/models/enums.py` (`VocabularyTermManagedBy`, `VocabularyChangeAction`, `VocabularyChangeStatus`) | **Adapt** | Keep the action enum (create/update/retire/reactivate). Replace the status enum. Drop `managed_by`. Geo enums: **discard** (already in `main`). |
| `backend/app/modules/masterdata/admin.py` | **Adapt** | Reuse `_validate`, `_check_reference`, `find_similar` (built on `main`'s `match.same_value`), `_snapshot`, the `base_revision` checks, row locks, `list_terms` and `_changes_out`. Remove `publish=true` on propose and self-publish. Writes become calls to the definer functions. |
| `backend/app/modules/masterdata/admin_router.py` | **Adapt** | Same route layout. Add `/submit`, `/approve` (step-up), `/history` and `/offers`. Remove publish-on-create. |
| `backend/app/modules/masterdata/admin_schemas.py` | **Adapt** | Good field limits and http(s)-only `source_url`. Replace `_clean` with `main:backend/app/modules/geo/formats.py:clean_text` (NFC, refuses Cc and Cf/bidi except ZWJ/ZWNJ). Add markup and personal-data screening, closed attribute keys, and the no-"Unknown" rule (ADR-0028 §9). |
| `backend/app/modules/masterdata/loader.py` (diff) | **Replace** | ADR-0028 §3 rules, the advisory lock and history writes. Port the "kept" report line (#35 has no conflict line; add one). |
| `backend/app/modules/masterdata/packs/*.json` (`category`, `fixed_membership`) | **Discard** | Not needed under per-vocabulary authority. |
| `backend/alembic/versions/20261105_7d4a2c9e1b60_master_data_admin_console.py` | **Discard** | Wrong parent. Encodes the per-term model. The downgrade silently loses curation (F7). Replaced by one new migration on `main`'s head. |
| `backend/alembic/versions/20261106_9e3b5d7f2a14_geography_reference.py` | **Discard** | Duplicates tables `main` already has with an incompatible model. |
| `backend/app/models/geo.py`, `modules/geo/{router,service,schemas}.py`, `cli/geo.py` | **Already in `main`** | `main`'s versioned model is accepted ADR-0019. |
| `backend/app/modules/geo/importer.py` | **Discard, port hardening** | Port to `main:modules/geo/formats.py`/`importer.py`: NUL/binary and empty-file refusal (`importer.py:131-145`), `MAX_ROWS` (`:51,159`), capped error lists (`:54,82-97`; `main` already caps problem lists at 50, `importer.py:238,333`, so only the NUL/empty/`MAX_ROWS` checks are missing). |
| `backend/app/modules/geo/admin.py`, `admin_router.py` | **Discard for now** | HTTP snapshot approval contradicts `main`'s read-only geo grants and ADR-0019's CLI activation. Revisit only through a new ADR (§8, increment 5). |
| `backend/tests/test_masterdata_admin.py` | **Adapt** | Reuse: ordinary users 404 (:95), CSRF (:111), lists only vocabularies (:120), no tree access (:142), reaches users without deploy (:171), drafts invisible (:203), stale edits (:267, :292), loader never overwrites (:308), duplicates (:327), retired values readable (:346), malicious input (:444), parent active (:458), pagination (:471), one open change (:510). Rewrite: MFA (:102) and four-eyes (:243). Delete: fixed sets (:408). |
| `backend/tests/test_geo.py`, `tests/fixtures/geo/*` | **Adapt (3 tests)** | Port the NUL/empty/row-cap tests onto `main`'s importer. The rest are model-specific. |

### Frontend and e2e

| File | Verdict | Justification |
|---|---|---|
| `frontend/src/pages/admin/MasterDataPages.tsx` | **Adapt** | Keep the layout, dashboard, term table, `TermHistoryDialog`, `ChangeCard` and `Pager`. Replace `PendingReviewsPage` (offers Publish on one's own change, shares one busy state). Replace the `is_system_admin`/`mfa_enabled` client gating with server 404 → not-found and 403 → step-up. Drop the geography tab and the "planned" astrology and religion cards. Use a card list under `sm`; the table is `min-w-[40rem]`. |
| `frontend/src/pages/admin/TermEditor.tsx` | **Adapt** | Keep the form, live duplicate check, `lang` handling and `ChangeDiff`. Remove "Publish now" and the status select. Add submit-for-review and a 409 stale/rebase prompt. Fix focus on lifecycle errors. Add `lang` on the alias, diff and duplicate labels. Translate enums in the diff. |
| `frontend/src/pages/admin/MasterData.test.tsx` | **Adapt** | Reuse the fetch-stub harness and fixtures. Rewrite the gating and publish-now scenarios. |
| `frontend/src/api/hooks/masterDataAdmin.ts` | **Adapt** | Query keys and invalidation match `main`. Endpoints change. |
| `frontend/src/api/types.ts`, `openapi.json`, `schema.d.ts` | **Replace** | Regenerate (`npm run gen:api`). |
| `frontend/src/App.tsx`, `components/layout/AppShell.tsx` | **Adapt** | Small diffs. The nav link needs a server-provided flag such as `UserOut.platform_capabilities`; that list holds only the caller's own capabilities, and only hides the link. |
| `frontend/src/i18n/locales/{en,hi}.json` (`mdAdmin.*`) | **Adapt** | 161 keys with parity and good translations. Rename the publish/status keys; add queue, approve, step-up and history keys. Drop the `geo*`, `geoAdmin` and planned keys. |
| `frontend/src/components/geo/PlaceCascade.tsx` (+test), `api/hooks/geo.ts` | **Already in `main`** | API-incompatible with `main` (`code`/`path` vs `lgd_code`/`ancestors`). |
| `frontend/src/pages/admin/GeoSnapshotsPage.tsx` | **Discard for now** | Depends on the HTTP geo admin. |
| `e2e/tests/master-data-admin.spec.ts` | **Adapt** | Reuse `seedSystemAdmin`, MFA enrolment, `expectAccessible` (axe) and the 404/leak checks. The core flow (one admin self-publishes) must become two admins. |
| `e2e/tests/geography.spec.ts` | **Already in `main`** | As `e2e/tests/lgd-places.spec.ts`. |

### Docs and CI

| File | Verdict | Justification |
|---|---|---|
| `docs/architecture/adr/0026-super-admin-master-data-console.md` | **Discard** | The number belongs to the accepted cultural-depth ADR. The content is superseded by ADR-0028. |
| `docs/architecture/adr/0018-…` amendments 1–2 | **Discard** | Amendment 1 marks itself "Accepted" without owner acceptance. Amendment 2 (religion/community lists) is rejected by the policy in §6. |
| `docs/architecture/adr/0019-indian-geography-reference.md`, `docs/operations/geo-import.md` | **Discard** | `main` has an accepted 0019 and `docs/operations/geo-reference-data.md`. |
| `docs/security/threat-model.md` T44/T45 rows | **Discard** | The IDs are already used on `main`. The console's threat is allocated in increment 1 (§6 A9). |
| `.github/actions/apt-install/*`, `ci.yml`, `renderer/scripts/ffprobe*.mjs`, `smoke.mjs`, `renderer/package.json`, `remotion-rendering.md` | **Superseded by #60** | Patch-identical. Land #60 on its own. |

## 4. Critical findings

**Security (PR #35 code)**

- **F1 — Critical: one admin can change every family's suggestions alone.**
  - `masterdata_require_second_admin` defaults to `False`.
  - `propose(…, publish=True)` publishes in the same request (`admin.py`, `propose` → `_publish`).
  - The pending queue offers Publish on the proposer's own change.
  - No database constraint backs the setting.
- **F2 — High: implicit capability.** Every `is_system_admin` account holds `MASTER_DATA_ADMIN`.
  - There is no grant record, revocation or audit of who may curate.
  - The demo seeder creates a system admin in dev/test.
- **F3 — High: MFA is checked per account, not per session.**
  - A session opened before TOTP was enabled, or opened by an attacker who then enrols their own TOTP, qualifies.
  - There is no step-up for publishing.
  - (This also affects ADR-0028's design; see A5.)
- **F4 — High: lost update between pack load and publication.**
  - The loader reads terms without a lock, decides on its in-memory `managed_by` value, then issues a plain UPDATE.
  - If a console publication commits between the read and the write, the UPDATE waits on the row lock and then overwrites the curated values.
  - The two paths share no advisory lock.
- **F5 — High: history is mutable.**
  - `vocabulary_change` is both the queue and the history.
  - The app role has full DML on it and on `vocabulary_term`, so a bug or injection elsewhere in the API can rewrite or delete history and terms.
- **F6 — Medium: label validation gaps.**
  - `_clean` collapses whitespace only, so RLO and other bidi or zero-width characters pass.
  - No NFC normalisation. No markup or personal-data screening.
  - Free attribute keys. "Unknown" terms are allowed.
  - A pravara link can be set to `reviewed` without a source.
  - Language labels are editable.

**Migration and governance**

- **F7 — Blocker: #35's migrations must not exist in the canonical chain.**
  - They fork `main`'s graph (two heads) and duplicate geography objects.
  - `7d4a2c9e1b60` encodes the rejected per-term ownership model.
  - Its downgrade resets curated terms to pack-managed, so the next `load` silently overwrites published work.
  - **Re-parenting them would carry all three defects.** Nothing on the pilot ran them, because #35 was never merged.
  - Developers who did must first `alembic downgrade 5c2d8e1f7a90` on the #35 checkout, or reset the database.
- **F8 — Process: document collisions.**
  - #35 reuses ADR-0026 (taken by cultural depth) and ADR-0019 (a conflicting second file), and threats T44/T45 (taken).
  - It marks its own ADR-0018 amendment "Accepted", and also its own ADR-0026 (console) and ADR-0019 files "Accepted" (status lines and README rows; the ADR-0019 line cites an owner go-ahead to start a phase). Both numbers collide with different accepted ADRs on `main`.
  - ADR-0028 and #62 both claim T63.

**Defects in ADR-0028 as written (found by stress-testing against `main`)**

- **F9a — "Pack proposals start `draft`, outside suggestions" is wrong on `main`.**
  - All 85 live terms are `draft`.
  - `_global_terms` excludes only `retired` unless `reviewed_only` is passed (`masterdata/service.py:104-108`).
  - So a pack proposal stored as `draft` **would be suggested to every family** before approval.
- **F9b — The grant and solo-mode tables are missing from §14's read-only list.**
  - If `platform_capability_grant` stays writable by the app role, an injection could grant the capability to itself.
- **F9c — §14's function list is incomplete.**
  - With change-request tables read-only, the API also needs functions to save or edit a draft, withdraw and reject, not only submit, publish and decide-offer.
- **F9d — `CHECK (approved_by <> submitted_by)` is NULL-permissive.**
  - Both columns are nullable FKs (`ON DELETE SET NULL` in #35's pattern), so a NULL passes the check.
- **F9e — Definer functions bypass RLS.**
  - RLS is not FORCEd and the functions run as the owner.
  - The offer projection is therefore a **cross-tenant read primitive** and must be built and tested as one.
- **F9f — The ADR's "verified main" context is stale** (`1f99b97`).
  - The read-only list is now five tables.
  - ADR-0029 exists.
  - The threat ID is contested.

## 5. Final recommended architecture

```
                       ┌──────────── operator CLI (schema owner) ─────────────┐
                       │ masterdata load / export / adopt-pack                 │
                       │ masterdata grant|revoke  (platform_capability_grant)  │
                       └───────────┬──────────────────────────┬───────────────┘
            pg_advisory_xact_lock(MASTERDATA) │                │ owner writes
                                      ▼                        ▼
 vocabulary(authority) · vocabulary_term(revision, curated) · vocabulary_term_version (append-only)
 vocabulary_change_request · vocabulary_pack_proposal · platform_capability_grant
        ▲  SELECT only for vanshavali_app                         ▲
        │                                                        │ EXECUTE only
 /api/v1/admin/master-data/*  ──▶  masterdata_* SECURITY DEFINER functions (search_path pinned,
   require_platform(MASTER_DATA_ADMIN)        same advisory lock, re-check author≠approver,
   + session MFA ≤12 h, step-up ≤15 min       base revision, authority=database, allow-listed key,
   no bind_tree, no tree-model imports        never DELETE, always write version row)
        │
 families: /vocabularies/* (unchanged; reads curated + pack terms; never sees proposals)
```

- **Source of truth.** Each vocabulary has an authority:
  - `pack` (default): the loader owns it.
  - `database`: the console owns it, and the pack is a seed and proposal channel.
- **Console-editable vocabularies.** An allow-list in code and repeated inside the definer functions: gotra, kula, kuladevata, kuladevi, devak, occupation.
- **Pack and code owned.** Language, honorific, pravara and kinship stay `pack`. Rashi, nakshatra and the enums stay in code.
- **No lists at all** for religion, community or caste.
- **Pack proposals** for `database` vocabularies go to a separate `vocabulary_pack_proposal` table, never into `vocabulary_term` (fixes F9a).
- **Stored family references stay valid without rewriting** (ADR-0018 §6), because:
  - records store code and label;
  - terms are never deleted and codes never reused;
  - retire and merge only change `status`/`replaced_by`.
- **Geography** stays on ADR-0019's CLI. The console shows snapshot status read-only.

## 6. ADR-0028: decisions and required amendments

**Owner policy decisions, stress-tested.**

| Decision | Verdict | Stress-test notes |
|---|---|---|
| Two named admins; defer solo mode | **Recommend: accept** | With one admin, the console can draft but not publish. The fallback is `export` → code review (Option A). Go-live of publication needs a second enrolled admin. Remove solo mode, `masterdata_solo_mode` and `approval_mode=solo` from the first migration; add them later by amendment if ever wanted. Residual risk is two colluding admins, mitigated by the audit, the version history and `export` before each deploy. |
| Offer notes never shown to global reviewers | **Recommend: accept** | Also recommend stopping collection of the note (ADR-0026 §4 amendment, a separate owner decision). Offers in the console are a later increment (6), not needed for the first publication. |
| Vocabulary tables read-only to the app role; restricted definer functions | **Recommend: accept with A2–A4** | Definer functions are themselves attack surface. Keep them few, owner-owned, `SET search_path = pg_catalog, public, pg_temp` (pg_temp last), `REVOKE EXECUTE … FROM PUBLIC`, no dynamic SQL. A migration test asserts `prosecdef`, `proconfig`, owner and grants. |
| Initial set: Gotra, Kula, Kuladevata, Kuladevi, Devak, Occupation | **Recommend: accept** | Three of these lists are empty, so adoption is trivial. Gotra (16), kula (7) and occupation (17) adopt their current pack rows as revision 1, `curated=false`. |
| Controlled enums, Rashi, Nakshatra, roles stay in code | **Recommend: accept** | Enforced three ways: the code allow-list, the definer-function allow-list, and a test that every `vocabulary` key outside the list refuses adoption. |
| Religion, community, caste: optional personal fields; no global or inferred lists | **Recommend: accept** | Reject #35's ADR-0018 amendment 2, its `religion_community` category and its "planned" card. |
| LGD and India Post need licensing and attribution review before real import | **Accept, with a gap** | `main` hard-codes `LICENCE = "GODL-India"` (`geo/importer.py:54`) and a constant attribution. Record licence and attribution per snapshot at staging (port the idea from #35). Refuse non-fixture files until the owner's review is recorded (increment 5). |

**Amendments required before acceptance.**

- **A1. Refresh the context to `main` at merge time.**
  - Read-only tables: five, including `panchang_day`.
  - ADR-0029 exists.
  - PR #35's migrations are discarded, not reused (§3).
- **A2. Add tables to `READ_ONLY_TABLES`:** `platform_capability_grant` and every new master-data table, not only the vocabulary ones. Grants and revocations are owner CLI only (F9b).
- **A3. Name the complete function set:**
  - `masterdata_save_draft`
  - `masterdata_submit`
  - `masterdata_withdraw`
  - `masterdata_reject`
  - `masterdata_approve_publish`
  - `masterdata_set_authority` (adopt or release, itself a second-admin change)
  - later, `masterdata_offer_projection` and `masterdata_decide_offer`

  Each takes the advisory lock where it writes terms, and each writes its own `audit_event` row (`tree_id NULL`) (F9c).
- **A4. Constraints.**
  - `CHECK (status <> 'approved' OR (approved_by IS NOT NULL AND approved_by <> submitted_by))`.
  - `submitted_by NOT NULL` once submitted.
  - User FKs `ON DELETE RESTRICT`. Accounts are anonymised on closure, not deleted (`identity/service.py`, close account) (F9d).
- **A5. Session MFA.**
  - Add `user_session.mfa_verified_at` and `user_session.mfa_step_up_at`.
  - A session qualifies only if `mfa_verified_at >= app_user.mfa_enabled_at`. This closes "disable, re-enable, old session still counts".
  - Add a `POST /auth/step-up {code}` endpoint, with a rate limit shared with login TOTP.
  - Google sessions never qualify.
  - Verify that password change and reset revoke other sessions; add a test either way.
- **A6. Pack proposals live in `vocabulary_pack_proposal`**, not as `draft` terms (F9a). Codes are reserved across terms, proposals and open requests.
- **A7. Defer merge and `replaced_by`** to after increment 4. Retire with an optional successor (from #35) covers the first release.
- **A8. Offer projection hardening.**
  - The function takes no tree id.
  - It returns only the §12 columns, for `offer_status = 'offered'`.
  - It is paginated and audited per call.
  - Tests prove it returns nothing else and refuses non-holders (F9e).
- **A9. Threat ID.** Allocate the next free ID when increment 1 merges (T64 if #62 lands first). Do not hard-code T63.
- **A10. Console switch.** `VSH_MASTERDATA_CONSOLE_ENABLED` defaults to `false` until the go-live checklist records two named admins.

## 7. Migration and consolidation plan

1. **No #35 migration lands.** All schema work comes in new revisions chained to `main`'s head at the time; today that is `d9b4f2c6a713`, or `f2a9c4e7d815` if #62 lands first.
2. **Increment 1 migration (identity)** adds:
   - `platform_capability_grant`, read-only to the app role;
   - `user_session.mfa_verified_at` and `mfa_step_up_at`, nullable. Existing sessions are NULL, so they do not qualify.

   Downgrade drops them; no data is at risk.
3. **Increment 3 migration (master data)**, purely additive:
   - `vocabulary.authority` (default `pack`) and `pack_version_seen`;
   - `vocabulary_term.revision` (default 1) and `curated` (default false);
   - `vocabulary_term_version`;
   - `vocabulary_change_request`;
   - `vocabulary_pack_proposal`;
   - the append-only trigger;
   - the definer functions;
   - the grant change.

   **Backfill:** one `vocabulary_term_version` row per existing term (revision 1, `source=loader`, current pack version). Term rows, codes and labels are untouched, so every stored family reference resolves as before.
4. **Downgrade of increment 3:**
   - refuses while any request is `submitted`;
   - refuses while any term is `curated`, unless `--i-exported` is set via an `-x` argument;
   - keeps every `vocabulary_term` row and value;
   - restores app-role DML.

   The runbook requires `masterdata export` first.
5. **Adoption** of the six vocabularies is a second-admin change after deploy, not part of the migration. Until then, behaviour is identical to today.
6. **Deploy safety.** Every deploy runs `alembic upgrade` and then `load`. `load` takes the advisory lock and never writes curated terms. `load --dry-run` in CI fails on any conflict in a `pack` vocabulary. The release runbook runs `masterdata export` before deploying.

## 8. Implementation PR sequence

Each increment is a draft PR from `main`, merged only with the owner's approval, and only after ADR-0028 (amended) is accepted.

| # | Branch (suggested) | Scope | Reuses from #35 |
|---|---|---|---|
| 0 | — | Land **#60** (CI) on its own. Accept **ADR-0028 + §6 amendments** (update #61). Add "amended by ADR-0028" notes to ADR-0006/0018/0026 in a separate change. | — |
| 1 | `claude/md-console-1-capability` | `platform_capability_grant` and CLI `grant/revoke` (verified email, TOTP, role-mailbox deny-list); session MFA columns, set at login; step-up endpoint; `require_platform`; `UserOut.platform_capabilities`; import-boundary test; threat ID; privacy-model section. | `authz/platform.py`, `AdminContext` |
| 2 | `claude/md-console-2-catalogue` | Read-only console: vocabularies (with authority badge), terms, term detail; not-found page; 403 step-up prompt; card list at 390 px. | `MasterDataPages.tsx` (layout, dashboard, table, pager), hooks, i18n keys |
| 3 | `claude/md-console-3-loader-history` | Migration from §7.3; loader rules and advisory lock; `export`, `adopt-pack`, `--dry-run` CI gate; version history view; read-only grants and definer functions (no publish yet). | Loader "kept" report, `revision` |
| 4 | `claude/md-console-4-review-publish` | Change requests: draft, submit, approve (second admin, step-up), reject, withdraw, stale; validator (`clean_text` + ADR §9); retire and reactivate; rollback-by-change; adoption of the six lists; two-admin e2e. | `admin.py` validation and concurrency, `TermEditor.tsx`, `ChangeDiff`, `test_masterdata_admin.py` (adapted), e2e scaffolding |
| 5 | `claude/geo-5-snapshot-admin` | Geography on ADR-0019 infrastructure: per-snapshot licence and attribution, licence-review gate, importer hardening (NUL/empty/row cap, CSV-formula neutralising in the change report), read-only snapshot status in the console. HTTP approval only by a new ADR. | `geo/importer.py` hardening, 3 tests |
| later | — | Offers in the console (A8), merge (A7), optional solo mode. | — |

## 9. Acceptance tests per increment

Every increment must pass `make check`, the Alembic round trip (`upgrade head → downgrade -1 → upgrade head`) on a seeded database, and the CI e2e job.

- **Increment 1**
  - A non-holder gets 404 on every `/admin/master-data/*` route, parametrised over all routes.
  - A holder with a session whose `mfa_verified_at` is NULL gets 403 `admin_mfa_required`.
  - Older than 12 h → 403.
  - `mfa_verified_at < mfa_enabled_at` (disable, then re-enable) → 403.
  - A Google session → 403.
  - TOTP turned off → the next request gets 404 or 403 (no cache).
  - A step-up older than 15 min → 403 on a write.
  - A revoked grant loses access on the next request.
  - The app role cannot INSERT/UPDATE/DELETE `platform_capability_grant` (direct SQL as `vanshavali_app`).
  - The grant CLI refuses an unverified email, no TOTP, and deny-listed mailboxes.
  - A holder gets 404 on every `/trees/{id}` route of a non-member tree (the parametrised route test).
  - Import-boundary test: the console modules import no tree-scoped models or services.
  - CSRF is required on writes; rate limit returns 429.
- **Increment 2**
  - Vitest:
    - 404 renders not-found;
    - 403 renders the step-up prompt;
    - `pack` vocabularies show no edit controls;
    - en/hi parity;
    - `lang="hi"` on Devanagari text.
  - Playwright:
    - axe WCAG 2.2 AA on each page;
    - 390 px with no horizontal page scroll;
    - a family member gets 404.
- **Increment 3**
  - Loader: each row of ADR-0028 §3 against a database with curated, retired and proposed terms.
  - Pack proposals are never returned by `/vocabularies/*`.
  - **Race:** run `load` and a definer-function publish concurrently, in two connections with a barrier; the curated values survive.
  - The version table refuses UPDATE and DELETE (as the owner via the trigger, and as the app role via grants).
  - Direct `INSERT/UPDATE/DELETE/TRUNCATE` on every master-data table as the app role fails.
  - Definer functions:
    - `prosecdef = true`;
    - pinned `search_path`;
    - owned by the schema owner;
    - EXECUTE granted only to the app role;
    - a `search_path` hijack (a shadow function in a temp schema) has no effect.
  - The migration round trip keeps every term and value. The downgrade refuses with a submitted change.
  - CI fails on a `pack` vocabulary conflict.
- **Increment 4**
  - Self-approval is refused by the service, the definer function (called directly) and the CHECK.
  - Two concurrent approvals of the same change: exactly one publishes.
  - A stale base revision → 409 and state `stale`.
  - Validator negatives:
    - bidi and zero-width characters, control characters;
    - markup;
    - email, URL and phone-like runs;
    - "Unknown";
    - growth of a closed list;
    - a pravara link without a source;
    - a non-allow-listed key → 404.
  - Retire keeps stored family values readable.
  - Every publish has one version row and one audit event, with no tree id in `details`.
  - **Curated values survive a deploy:** publish, run `alembic upgrade head` and `load`, and the value is unchanged.
  - e2e: admin A drafts, admin B approves with step-up, and a family sees the suggestion without a deploy.
- **Increment 5**
  - Malicious files are refused:
    - NUL or binary content;
    - an empty file;
    - more than `MAX_ROWS` rows;
    - bidi characters;
    - formula-prefixed names, neutralised in the CSV report.
  - A non-fixture import is refused until the licence review is recorded.
  - The snapshot stores licence and attribution.
  - The app role still cannot write the geo tables.

## 10. Supersession (only after verified parity)

| PR | Recommended outcome | Condition |
|---|---|---|
| #60 | Merge on its own (owner decision) | Already green, and patch-identical to #35's CI commits. |
| #61 | Update with the §6 amendments, then accept | Owner decision. |
| #35 | Close as **superseded** | After increment 4 merges and §3's "adapt/reuse" items are verified present. Keep the branch for reference. |
| #62 | Unaffected | Only coordinate the threat ID and the Alembic parent with increment 1/3. |
| #19 | Out of scope | Separately already superseded by ADR-0018 and ADR-0019 on `main`. |

## 11. Open owner decisions

1. Accept ADR-0028 with amendments A1–A10.
2. Stop collecting `offer_note` for new offers (amends ADR-0026 §4)?
3. Name the two initial administrators for go-live.
4. Licence review for real LGD and India Post files, and who records it.
5. Should geography snapshot approval ever move to HTTP? It needs a new ADR; the recommendation is to stay on the CLI.

## Addendum: re-check of 11 Nov 2026 at `3cb12f9` (integration audit)
- `main` changed only in the agent ticket factory, CI and an overload test since `5913759`; the
  findings above still hold. ADR-0028 has since been amended with A1–A10 (#61); F9a–F9f describe
  the text **before** those amendments.
- "Recommend: accept" in §6 is this review's recommendation, not a status. ADR-0028 stays
  **Proposed** until the owner accepts it.
- Draft PR #67 (increment 1) uses T64 and migration `e7c2a9f4b310`, which revises `d9b4f2c6a713`
  like #62's `f2a9c4e7d815`; whichever merges second must re-parent so `main` keeps one head.
- **#35 work not classified above:**
  - `masterdata/schemas.py`, `service.py`: `revision` (cache refresh) and `successor_code` in the
    public `/vocabularies` output. Worth porting with retirement (increment 4) so families see a
    retired term's successor.
  - Tests `test_reject_needs_a_note_and_only_the_proposer_withdraws` (maps onto reject/withdraw,
    increment 4) and `test_new_tree_after_publication_sees_the_term` (adapt, increment 4).
  - `models/genealogy.py`, `genealogy/schemas.py`, `pages/tree/PlacesPage.tsx` (`lgd_level` on
    places): already in `main` through ADR-0019; discard.
  - Docs (`privacy-model.md`, `data-model.md`, `domain-model.md`,
    `india-master-data-and-smart-forms-plan.md`, `dev-accounts.md`, `IMPLEMENTATION_STATUS.md`,
    `CLAUDE.md`), `api/router.py`, `describe_schema.py`: rewrite per increment; do not copy.
  - F7 also applies to history: the `7d4a2c9e1b60` downgrade drops the whole `vocabulary_change`
    table.
