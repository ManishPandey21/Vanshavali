# Family profile acceptance and verification matrix

Status: planned tests unless a result is explicitly recorded below. This is not a claim that the
new features exist. Scope is the [brief](brief.md); design is [ADR-0031](../adr/0031-family-profile-addresses-and-communications.md).

## Baseline verified on 12 November 2026

- Main baseline `b8c248bc1a4802dd90552b20a5ded3738f400d20`; changes since the environment's earlier
  full application check are the merged factory launcher fix only.
- `alembic heads` and development DB `alembic_version`: one head, `a4d7e2c9b153`.
- Development `geo_snapshot`: zero rows. National PIN coverage not tested/available here.
- Targeted backend command:
  `uv run --frozen --no-sync pytest -q tests/test_genealogy.py tests/test_privacy.py tests/test_geo.py tests/test_reminders.py tests/test_threat_model_ids.py`.
  **78 passed, 0 failures/errors/skips in 78.15 s**, JUnit evidence in the setup artifacts at
  `/workspace/artifacts/vanshavali-setup/profile-audit-tests.xml`. Tests use their isolated test database,
  including synthetic reference fixtures; no invitations or external provider messages are sent.
- Frontend command:
  `npm test -- --run src/components/geo/PlaceCascade.test.tsx src/pages/tree/person/profile.test.tsx src/i18n/i18n.test.ts`.
  **17 passed across 3 files**, 5.27 s. Both commands exited 0.

The previous environment check covered full backend/frontend/E2E/visual/renderer suites. This
design change does not rerun all of them or claim they verify unimplemented features. Fresh browser
acceptance is required at every implementation increment.

## Required regression and acceptance tests

| ID / increment | Backend / migration contract | Frontend / real-stack proof |
|---|---|---|
| FP-A01 / A | Same birth event ID after date/time/place edits; other claims/participants/evidence unchanged; updates carry revision | Create member → edit all three fields separately → save/reopen/reload; preferred and alternate claim selection |
| FP-A02 / A | Year-only, month/year, circa, before/after/range/unknown preserved; withheld has NULL date/sort; no invented components | Manual and picker entry, precision switches, unknown versus withheld versus hidden, en/hi |
| FP-A03 / A | Time source/precision validation; seconds/zone/offset roundtrip; no inferred UTC/timezone; date edit cannot clear hidden time | 12-hour midnight/noon and 24-hour entry, seconds, unknown/approximate, no automatic zone |
| FP-A04 / A0 | Per-field view/edit on direct create/update, imports/extraction, proposal approval/revert; 404 cross-tree, no admin bypass | Hidden controls and no private payload in responses/DOM; forged API requests still denied |
| FP-A05 / A0 | Role promotion leaves strict audience unchanged; remove/reinvite loses grants; orphan controller cannot be reclaimed; claim resets contributor access | Claimed and unclaimed profiles; exact audience preview; widening confirmation and stale preview refusal |
| FP-A06 / A | Review-all causes proposal, authorized independent reviewer required, stale edit atomic, revisions redacted | Save → rationale → review → accepted fact; forbidden/missing/loading states recoverable; cancel no write |
| FP-A07 / A2 | Move date earlier/later; pending/retry occurrence invalidated; unknown/withheld pauses; changed privacy cancels; no duplicates across repeated ticks or date reversal | Set birthday reminder → edit date → updated next occurrence/paused status after reload |
| FP-A08 / A2 | Concurrent event edit and provider invocation in both orders; explicit residual for already accepted send; revoked channel consent stops pending send | Mock provider outbox only; no real messages; birthday requires no birth time |
| FP-B01 / B | Existing PIN lookup: one/many/no offices, invalid PIN, disabled/no snapshot; state/district ancestors; version provenance | Valid PIN auto-query, no lookup before validity, unique untouched draft suggestions, office selection, no village/street guess |
| FP-B02 / B | Reverse PIN precision is district/sub-district candidate when exact relation absent; unknown code empty/error without invention | Name/alias/Hindi search, same-name village disambiguation, parent reset, mismatch keep/replace |
| FP-B03 / B | Approved importer unchanged; no tree text in reference data; snapshot rename never rewrites recorded names | Slow stale response discarded; manual/overseas entry works offline from reference dataset; no forced Indian PIN |
| FP-C01 / C | Multiple purposes/current residences, at most one explicitly primary current, composite FKs and RLS | Add/edit/remove separate cards; authorized current city independent of street visibility |
| FP-C02 / C | Move atomic; selected old record retained; approximate/unknown validity unchanged; stale concurrent move conflicts; idempotent retry | Change current address → old shown in history; correction creates revision rather than fabricated move |
| FP-C03 / C | Full address/history/contact never leaks through Place list, search, maps, exports, audits, source previews, proposals, recents or counts | Unauthorized private-address read denied; UI does not fetch hidden detail to render coarse city |
| FP-C04 / C | Empty migration roundtrip; populated lossy downgrade refused unchanged; verbatim idempotent encrypted legacy conversion and compatible restore | Old-client write cannot create divergent legacy value; legacy record labelled unknown purpose/dates |
| FP-D01 / D | Ancestral assertion reused; snapshot/local/historical names retained; property reference grants no interest | Add ancestral village → choose for another authorized member → confirm → reopen; branch suggestion optional |
| FP-D02 / D | Link pins version, copy has independent payload but original privacy ceiling; revoke/erase across copy chains; cross-tree source rejected | Copy/edit leaves source unchanged; shared correction preview/adoption; no hidden affected-person count |
| FP-D03 / D | Duplicate geographical match offers existing place; historic variants allowed; commit rechecks source rights | Searchable source picker; my-address unavailable without linked profile; no auto ancestral assignment |
| FP-E01 / E | AES-GCM storage and no plaintext history/proposals; masked default and authorized reveal; syntax validation | Same-as-mobile explicit, later change prompts; safe Telegram/Instagram profile links, no send |
| FP-E02 / E | Person contact is not user endpoint; no inherited verification/consent; role change grants no private read | Claimant separately verifies/opts in; relative-entered endpoint labelled unverified |
| FP-F01 / F | Claim invitation requires consent/admin approval; forwarded link no membership; email invite matches verified recipient; scope/expiry/revoke/rate limits | Invite → approved joining flow using local mock mail; Telegram/WhatsApp manual share generic, no private preview; truthful statuses |
| FP-G01 / G | Multiple marriage events retain participants and per-event subscriptions; incomplete/disputed date never guessed | Create marriage → choose exact event → set anniversary reminder; 0/1/7/custom/timezone/language |
| FP-H01 / H | Telegram nonce hashed/expiring/single-use; reject forged webhook, group chat, replay, account swap; unlink cancels | Initiate/link/confirm/revoke through mocked official API; username alone disabled |
| FP-I01 / I | Purpose-specific verification/invitation/reminder template selection; disabled adapter refuses; consent checked on delivery | Only approved available channels offered; template/provider failure shown without recipient data |
| FP-J01 / J | SMS DLT/consent evidence gate; no Instagram DM or Chatwoot runtime dependency | Profile links only; optional evaluation produces a dated decision, no traffic |
| FP-X01 / all | Route isolation test discovers every new tree endpoint; fixtures exercise owner/admin/branch/contributor/researcher/viewer/claimant/nonmember | 390 px, keyboard focus, large text, en/hi parity, axe, no horizontal overflow; manual native-language/screen-reader review recorded separately |

Existing regression anchors: `test_genealogy.py` (incomplete dates, competing claims, historical
places), `test_privacy.py`, `test_geo.py` (PIN upper-level-only, aliases, snapshot provenance),
`test_reminders.py` (recipient privacy, verification, retry), `test_proposals.py`,
`test_route_isolation.py`, `test_rls.py`, `test_migrations.py`, `test_onboarding.py`,
`test_calendar.py`, and the existing frontend profile/geo/date tests. Add focused tests for gaps;
do not weaken old assertions or replace security coverage with implementation-shaped tests.

## Completion evidence per implementation PR

Record base/head SHA, migration parent/head, fixture provenance, commands/results, expected skips,
negative tests, generated API files, screenshots or trace for new browser flows, and separate
standards/spec reviewer findings. Existing tests passing establishes regression safety only;
new acceptance rows must be proven before that increment is marked complete.
