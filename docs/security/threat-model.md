# Threat model

Status: STRIDE model, kept in step with the implementation. Revisit whenever auth, authorisation,
sharing, uploads, downloads, exports, admin or public features change.

## 1. Assets
- Living people's and children's personal data (DOB, birth time, contact, address).
- Caste, community and religion data.
- Kundli and astrology data.
- Birth certificates, wills, deeds and land records (identity-bearing, and valuable for fraud and
  litigation).
- Property interest records: a forged lineage or forged shares could be used to support claims.
- Account credentials and sessions.
- Integrity of the archive itself.
- Encryption and signing keys.

## 2. Actors
- Anonymous visitor.
- Public-page reader.
- Tree `VIEWER`, `RESEARCHER`, `CONTRIBUTOR`, `BRANCH_ADMIN`, `DOCUMENT_CUSTODIAN`,
  `PROPERTY_CUSTODIAN`, `FAMILY_ADMIN`, `OWNER`.
- Platform `SYSTEM_ADMIN` (no tree access).
- A malicious insider, e.g. a relative in a property dispute.
- Background worker.
- A compromised dependency.

## 3. Trust boundaries
- Browser ↔ nginx/API (TLS, cookie session, CSRF).
- API ↔ PostgreSQL.
- API/worker ↔ object storage (ciphertext only).
- API ↔ clamd.
- Queue ↔ worker.
- Import files (untrusted GEDCOM and documents) ↔ parsers and OCR.

## 4. Threats, controls and tests

| # | STRIDE | Threat | Control (implemented) | Test |
|---|---|---|---|---|
| T1 | I / E | **IDOR/BOLA**, cross-tree access to any resource | Tree context resolves membership, and non-members get **404**. Every lookup uses `tree_id` (`lookup.get_in_tree`). Composite `(tree_id, id)` FKs make cross-tree references impossible in the DB. **Postgres row-level security** (ADR-0002 §7) is a second barrier: the app role only sees and writes rows of the tree bound to the transaction. | `test_rls.py`, `test_route_isolation.py` (every `/trees/{tree_id}` route, stranger and anonymous), `test_privacy.py::test_cross_tree_access_is_404`, `test_heritage_family.py::test_citation_cannot_target_other_tree` |
| T2 | E | Viewer or researcher edits through the API | Deny-by-default permission matrix and `ctx.require()` on every mutation. Branch scope limits branch-scoped roles. | `test_privacy.py::test_viewer_cannot_modify_anything_via_api`, `::test_branch_scoped_contributor`, Playwright flow 4 |
| T3 | E | Self-promotion, or removing the last owner | Only an OWNER grants or removes OWNER/FAMILY_ADMIN. No self-role change. The last owner can't be removed. Invitations are bound to an email and single-use. | `test_trees.py` |
| T4 | I | Living person or minor leaks via API, search, public page, graph, export, hydration or HTML | Central privacy evaluation plus serialiser redaction. Hidden relatives become placeholders. Public mode shows deceased people only. The SPA shell has no data. `noindex` is set. | `test_privacy.py` (DOB/time/contact never in raw JSON; public pages; minors), `test_search_consent.py`, `test_gedcom.py` |
| T5 | I | Download URL reuse, expiry bypass or guessing | HMAC-signed token bound to document, user, variant and expiry (≤300 s). Authorisation is re-checked at download time. `no-store`. Private bucket; app-level encryption. | `test_documents.py` |
| T6 | T / E | Malicious upload (polyglot, PDF JS, zip/decompression bomb, SVG XSS, EICAR) | Magic-byte allowlist (no SVG/HTML). PDF JS, launch and encryption rejected. Page and pixel caps. clamd scan before storing (fail-closed). `attachment` + `nosniff`. EXIF stripped from previews. | `test_documents.py` |
| T7 | T | OCR/AI output (or prompt text inside a document) silently changes facts | Extraction writes `extraction_proposal` rows only. Canonical changes need `review` by a user with `extraction.review`, and create *new* claims with citation and provenance. | `test_extraction.py` |
| T8 | R | Disputed edits to lineage or property | Append-only `audit_event` (a DB trigger blocks UPDATE and DELETE). All mutations audited without sensitive values. Reversible merge log. | `test_trees.py::test_audit_table_is_append_only`, `test_merge.py` |
| T9 | S | Credential stuffing, session theft | Argon2id. Per-IP and per-email login rate limits. Generic errors and dummy-hash timing equalisation. Optional TOTP MFA. HttpOnly SameSite=Lax cookies; `Secure` in production. Server-side sessions with idle and absolute expiry. Revoke others / password change revokes. | `test_auth.py` |
| T10 | T | CSRF | Double-submit token required on every unsafe method for cookie-authenticated routes | `test_auth.py::test_csrf_required_for_unsafe_methods` |
| T11 | I | Enumeration of people or trees | UUIDv7 ids, 404 for everything not visible, no counts of hidden rows | `test_route_isolation.py` |
| T12 | E | System admin browses family content | `is_system_admin` grants no tree permissions (not referenced by authorisation at all) | code review, ADR-0006 |
| T13 | I | Export exfiltration | Export requires `gedcom.export`, applies the exporter's privacy view, excludes living people by default. Sensitive export needs `privacy.manage`. Audited. | `test_gedcom.py` |
| T14 | D | Deep or wide traversal, huge uploads, pathological GEDCOM | Depth caps (≤25), node cap (500), upload size cap, parser record caps, a per-statement timeout on every app connection (`VSH_STATEMENT_TIMEOUT_MS`, 15 s) | `test_genealogy.py`, `test_gedcom.py`, `test_observability.py::test_statement_timeout_applies_to_app_connections` |
| T15 | T | Tampering with stored originals | Write-once keys (local `O_EXCL`, S3 `If-None-Match`). SHA-256 recorded. AES-GCM authentication detects modified ciphertext. | `test_documents.py` |
| T16 | I | Key compromise / bucket leak | Separate STANDARD and VAULT keys. Keys only from a secret manager (production config refuses dev keys). | `core/config.py` validator |
| T17 | S / T | Forged property shares presented as title | `legal_notice` on every property response. The documented-share invariant is ≤ 1. Status distinguishes asserted, documented and disputed. | `test_property.py` |
| T18 | I | Analytics/log leakage | No analytics SDK. Audit `details` hold field names only. Documents are never logged. Access logs record the route template only, never the raw path or query string (signed download tokens), with Uvicorn's access log off. Metrics use route templates and need a bearer token. Purged documents are audited without their title. | `test_observability.py`, `test_retention.py` |
| T19 | I | Account enumeration via registration, password reset or verification resend | **Closed (SEC-12).** Registration always answers `202` with one generic body and always hashes the password; an existing account's owner is emailed a "someone tried to register" notice instead of a verification link. Reset request and resend are always `202`. Unverified login is refused (`email_not_verified`) only after the correct password. All are rate limited per IP and per email. | `test_security_audit.py::test_registration_does_not_enumerate_accounts`, `test_email_auth.py` |
| T20 | I / R | People added without any accountability for having their permission (DPDP) | Server-enforced family-data attestation per user and tree before any person is created (UI, relatives, GEDCOM). The server owns the wording; the version, language and SHA-256 of the exact text are stored. Unticked by default. Withdrawal is audited. This is **not** treated as the relatives' consent (ADR-0011). | `test_onboarding.py` (`test_adding_people_requires_attestation`, `…per_user_and_per_tree`, `…stale_or_unknown_wording`, `…withdrawal…`) |
| T21 | S / E | A forwarded or leaked WhatsApp claim link is used by the wrong person | The link only files a claim; **no access until a tree admin approves**, and admins see the claimant's name and email. Single use (row lock), 7-day expiry, revocable, 256-bit token stored hashed. An existing member's roles are never widened. Contributors can offer VIEWER only. Branch scope is carried over. | `test_onboarding.py` (`test_claim_invite_happy_path`, `…single_use…`, `test_rejected_claim_gives_no_access`, `test_invite_permissions`, `test_approval_keeps_an_existing_members_roles`, `test_branch_scoped_inviter_cannot_widen_scope`) |
| T22 | I | Claim links leak living-person data (logs, Referer, link previews, message text, used or expired links) | Token in the URL **fragment** (never sent to servers or crawlers). The SPA shell has no data. The share message contains only the link, and `wa.me` is used with no phone number. The preview needs sign-in and shows names only. Used, expired, revoked and erased links reveal nothing (410/404). Tokens never go into the audit log. | `test_onboarding.py` (`…leaks_nothing_once_used`, `test_expired_and_revoked_invites`, `test_erasure_revokes_outstanding_invites`, `…audited_without_tokens`), Vitest `onboarding.test.tsx`, Playwright `onboarding-whatsapp.spec.ts` |
| T23 | E | Claim invites for minors, the deceased, hidden or cross-tree people | Refused for recorded minors, deceased/presumed-deceased and already-claimed profiles. The claimant must confirm they are 18+. Person lookup is visibility-checked and tree-scoped (404). | `test_onboarding.py` (`test_cannot_invite_for_deceased_minor_or_claimed_profiles`, `test_hidden_person_cannot_be_invited`, `test_claim_invites_are_tree_isolated`, `test_accept_requires_consent_and_adult_confirmation`) |
| T24 | S / E | Emailed token theft or replay (verification, password reset) | 256-bit tokens, SHA-256 at rest, single use, 48 h / 1 h expiry, newer token kills older, password change kills reset links, reset revokes every session. Tokens are never audited and are redacted from console mail logs outside development. Links contain no third-party resources (no referrer leak) and the API sends `Referrer-Policy: no-referrer`. Where to continue after verifying (`next`) travels in the link's **fragment**, so a claim-invite token carried there (T22) never reaches a server or its logs. | `test_email_auth.py` (incl. `test_claim_link_token_in_next_never_reaches_a_server`), Playwright `onboarding-whatsapp.spec.ts` |
| T25 | T / D | A forwarded or leaked claim link used to hide or erase someone's profile ("remove me"), or a real removal request ignored | "Remove me" only hides the profile (reversible) and files a request; **erasure needs an owner or family admin**, who sees the requester's name and email. "This isn't me" changes no person data. Claimed profiles can't be touched through a link. Other links are revoked, and new invites and claims are frozen while a request is open. Declined links reveal nothing afterwards. | `test_onboarding.py` (`test_not_me_cancels_the_link_and_changes_nothing`, `test_remove_me_hides_at_once_and_admin_erases`, `test_declined_removal_restores_visibility`, `test_remove_me_needs_confirmation_and_an_admin`, `test_remove_me_cannot_touch_a_claimed_profile`), Vitest `onboarding.test.tsx`, `ClaimsRemoval.test.tsx`, Playwright `claim-removal.spec.ts` |
| T26 | S / E | Sign in with Google abused: login CSRF, code interception/replay, forged or foreign ID token, open redirect via `next` | Off unless configured. Authorization code + **PKCE (S256)**, run server-side. `state`, `nonce`, verifier and `next` travel in an **HMAC-signed, purpose-bound, 10-minute, HttpOnly cookie** scoped to the callback path, and are checked in constant time; the cookie is single use. ID token taken only from Google's token endpoint over TLS and checked for `iss`, `aud`/`azp`, `exp`/`iat` and `nonce`. `next` is a same-origin path, signed inside the cookie. Failures redirect with a short code only (no tokens or claims) and are audited. (ADR-0012) | `test_account_security.py` (`test_state_must_match_this_browsers_cookie`, `test_tampered_or_foreign_signed_state_is_refused`, `test_state_cookie_is_single_use`, `test_bad_id_tokens_are_refused`, `test_next_cannot_redirect_off_site`, `test_token_exchange_failure_creates_nothing`, `test_google_is_off_unless_configured`), Vitest `AccountSecurity.test.tsx` |
| T27 | S / E | Account takeover through Google linking (someone else's Google account with the victim's email; pre-registration squatter; bypassing TOTP) | Accounts are matched by Google `sub`, never by email after the first link. Linking by email needs `email_verified` **and** a Google-authoritative address (gmail.com/googlemail.com or Workspace `hd`); other addresses must use the password. Linking an unverified (squatted) account replaces its password and revokes every session. MFA-enabled and closed accounts are refused. (ADR-0012) | `test_account_security.py` (`test_returning_google_user_matches_by_subject_not_email`, `test_non_google_address_needs_the_password_first`, `test_pre_registration_squatter_loses_access_when_owner_signs_in_with_google`, `test_mfa_accounts_cannot_bypass_totp_with_google`, `test_inactive_account_cannot_sign_in_with_google`) |
| T28 | S / E | A temporary (demo) password is shared or leaked and keeps working | Demo accounts come only from a CLI that refuses outside `development`/`test`, reads the password from an environment variable (never argv, source, seeds or docs) and stores only the Argon2 hash. `must_change_password` makes **every** authenticated endpoint except change-password and logout answer `403 password_change_required` (also after Google sign-in); the new password must differ; the change revokes other sessions. | `test_account_security.py` (`test_demo_account_must_change_password_before_anything_else`, `…rejects_reusing_the_temporary_password`, `…lifts_the_block`, `test_demo_account_refused_outside_development_and_test`, `test_demo_cli_reads_password_only_from_env`), Vitest `AccountSecurity.test.tsx` |
| T29 | T / D / I | A malicious GEDCOM photo package (zip bomb, path traversal, encrypted or nested archives, disguised or infected files, photos of hidden people leaking) | Never extracted to disk; members read one at a time with bounded reads; ≤5,000 entries, total ≤ `max_gedcom_package_bytes`, each photo ≤ `max_upload_bytes`, ratio >100:1 refused; encrypted and nested archives ignored; member names used only for matching. Every photo goes through the normal document pipeline (magic-byte allowlist, malware scan failing closed, encrypted write-once storage); rejected files are skipped and audited. A photo takes its person's privacy level (the strictest when shared). Files nobody references are never stored. (ADR-0013) | `test_gedcom_photos.py` (`test_package_safety`, `test_package_limits_are_enforced`, `test_a_photo_with_malware_is_skipped_and_the_rest_imports`, `test_a_non_image_is_rejected_and_a_pdf_is_not_filed_as_a_photo`, `test_photo_privacy_follows_the_person`, `test_photo_import_is_tree_scoped_and_needs_import_rights`), Playwright `gedcom-photos.spec.ts` |
| T30 | S / D / R | A client forges its IP with `X-Forwarded-For` to dodge per-IP rate limits (login, registration, resets) and to falsify audit and session IPs | **Found by the first DAST run (Oct 2026) and fixed.** The API trusts forwarded headers only from the proxies directly in front of it (`FORWARDED_ALLOW_IPS`: the nginx container's exact address, plus the load balancer in production), never `*`. uvicorn walks the header right to left, skipping trusted hops, so a client-supplied leftmost entry is never used. Trusting a whole Docker subnet is also wrong: the bridge gateway is where host clients appear. | `test_proxy_headers.py` (spoofed hop ignored; untrusted peer ignored; LB hop skipped; shipped Dockerfile, compose and DAST configs never trust `*`); `dast.yml` step "A client cannot choose its own IP" |
| T31 | I | Personal data in operational logs and job stores: the background worker logged each job's description, which RQ builds from the call **with its arguments**, so email jobs put recipients' addresses and subjects into the worker log, and failed jobs kept them in Redis for a year. GEDCOM import failures logged the parser's message, which can quote lines of the family file | **Found by the pilot audit (Oct 2026) and fixed.** Jobs run through `run_job` with a name-only description; the worker (`app.cli.worker`) disables RQ's description logging; failed jobs expire after 7 days; mail failures log the exception type and a masked address; import failures log the exception type and code location only. Caddy, the pilot edge, has no access log (signed URLs) | `test_pilot_ops.py` (`test_email_jobs_do_not_carry_addresses_into_worker_logs`, `test_failed_delivery_is_counted_retried_and_logged_without_content`, `test_gedcom_staging_failure_is_counted_and_logs_no_file_content`) |
| T32 | E / I | Unsafe deployment configuration turns off a control silently: `FORWARDED_ALLOW_IPS=*` (T30 again), CORS `*` with credentials, a plain-http public URL (cookies and links), dev or short keys, a `@localhost` sender; an application DB role that gained SUPERUSER/BYPASSRLS or owns the tables (RLS bypassed) | **Pilot audit (Oct 2026).** Production refuses to start with any of these (`Settings.validate_production`); loopback-only proxy trust logs a warning. `ensure_app_role` verifies on every release that the app role has none of SUPERUSER, BYPASSRLS, CREATEDB, CREATEROLE and owns no table, and stops the release otherwise; `/health/ready` already fails in production when RLS is bypassed. The pilot compose pins the only proxy (Caddy) and the test suite checks the pairing | `test_pilot_ops.py` (production guards), `test_app_role.py`, `test_proxy_headers.py::test_pilot_backend_trusts_exactly_the_caddy_address` |
| T33 | D | Object-store outage or revoked credentials surface as unhandled 500s and silent worker failures | **Pilot audit.** Storage errors are a structured `503 storage_unavailable` (type logged, no keys or bucket names), counted (`vsh_events_total{event="storage_error"}`) and alerted (`StorageErrors`) | `test_pilot_ops.py::test_storage_failures_are_a_structured_503` |
| T34 | I / E | **Heritage milestone:** a private event, its photos or its reminder reached through a new endpoint (album, life-events listing, story, map, reminders, render payload) when only the person, not the event, was checked | `get_event_checked` enforces the event's own privacy level for every lookup; listings and story/map/render go through the event serialiser and `visible_subjects`; album entries need both the event and the document to be visible; counts only count visible photos (ADR-0015) | `test_life_events.py` (`test_private_events_and_people_never_listed`, `test_photo_privacy_inherits_from_event_and_person`, `test_album_is_tree_isolated`), `test_visualization.py::test_viz_endpoints_leak_nothing_hidden`, Playwright `heritage-visualization.spec.ts` |
| T35 | I | Exact location of a living family's home disclosed via place or event coordinates, maps or exports | `coordinate_privacy` coarsens to 0.1° below the level (no geo note); event coordinates at such places coarsened; a coarsened view cannot be written back; public pages get no coordinates; no third-party map tiles or geocoders (ADR-0015, ADR-0017) | `test_life_events.py::test_coordinate_privacy_coarsens_for_lower_roles`, `test_visualization.py::test_map_points_paths_and_coordinate_privacy`, Vitest `geo.test.ts` |
| T36 | I / E | Animated export leaks private people or photos (payload built with more rights than the requester, artifacts readable by others, signed link replay, payload left in storage or logs) | Payload built as the requester from the viz APIs; photos embedded only if the requester may open the content (derivatives only, ≤ 600 KB); payload encrypted and purged in every terminal state; renderer runs with no `VSH_*` env, a 0600 temp file, a timeout, and its output is never logged; artifacts requester/admin-only; 5-minute user-bound signed URLs re-authorised at download; per-user and per-tree quotas (ADR-0017) | `test_render_jobs.py` (`test_payload_is_built_as_the_requester`, `…embeds_only_photos_the_requester_may_open`, `test_jobs_and_artifacts_are_private_to_the_requester`, `test_validation_quotas_and_failures`) |
| T37 | I / S | Reminders disclose family data or are abused: subscribing to others' dates, reminders surviving revoked access, names in SMS/WhatsApp via third parties, phone-number harvesting, OTP brute force, provider credentials or message bodies in logs | Per-user opt-in reminders, private to their owner (404 for others); visible full dates only; re-check as the recipient at send time (cancel with reason); SMS/WhatsApp texts carry no names/places/notes; delivery rows hold no body or address; phone numbers AES-GCM encrypted, masked, verified by 6-digit HMAC-hashed codes (10 min, 5 attempts, 5 codes/hour); provider errors stored as short codes only; credentials only from the environment; production refuses mock providers (ADR-0016) | `test_reminders.py` (`test_reminder_needs_the_visible_full_date`, `test_visibility_is_rechecked_at_send_time`, `test_removed_member_gets_nothing`, `test_reminders_are_private_to_their_owner`, `test_phone_contact_verification_and_encryption`, `test_contact_verification_attempts_are_limited`, `test_sms_reminder_carries_no_names_and_retries_then_fails`, `test_production_refuses_mock_providers`) |
| T38 | D | Expensive visualizations or renders exhaust the API or worker (deep fans, huge graphs, long videos, malicious uploads into albums) | Depth/radius/node/row/point caps on every viz API; graph expansion on demand; renders on a separate queue and worker with timeouts, duration (≤ 120 s) and payload (8 MB) caps and quotas; album photos go through the normal upload pipeline (magic bytes, malware scan, size/pixel caps) and albums hold ≤ 200 photos (ADR-0017) | `test_render_jobs.py::test_validation_quotas_and_failures`, `test_life_events.py::test_album_write_permissions_and_validation` |
| T40 | I / E / T | **Smart Add Relative (ADR-0020):** the multi-step add reveals hidden relatives through its candidate lists or term paths, links people from another tree, writes people the user never saw, creates a duplicate parent next to a hidden one, or an undo removes someone else's records | Plan endpoint writes nothing and lists only `visible_subjects`; hidden relatives are a count, never identified, and block a new provisional parent; commit recomputes the plan and refuses any choice not in it (422), so cross-tree or unrelated IDs never link; anchor lookup is tree-scoped (404); `PERSON_WRITE` on all three endpoints plus the existing relationship write checks; one transaction; undo only by the committing user, within 30 minutes, once, tree-scoped, and only while the created people have no other relationships; the virtual parent used for explicit siblings is stripped from every path and common-ancestor list; audit details hold IDs only | `test_smart_add.py` (`test_plan_writes_nothing_and_offers_the_recorded_mother`, `test_hidden_parent_is_counted_never_shown_and_blocks_a_duplicate`, `test_invalid_and_cross_tree_choices_are_refused`, `test_viewer_cannot_plan_commit_or_undo`, `test_undo_removes_exactly_what_was_added`, `test_undo_refused_once_the_new_person_is_connected_elsewhere`, `test_undo_is_tree_scoped`, `test_explicit_sibling_from_the_classic_dialog_resolves_uncle_and_cousin`), Playwright `smart-add.spec.ts` |
| T42 | I | **Age-aware kinship (ADR-0020 amendment):** an age-dependent term (Tau vs Chacha) reveals a living relative's full birth date (month/day) to a viewer allowed only the year, or reveals anything about a relative hidden from the viewer; an age order is recorded between people the user may not edit or see | Dates are compared from the viewer's privacy-redacted birth events (year-only where `BIRTH_DATE_FULL` is not visible); competing birth claims and overlapping ranges give "unknown"; pairs involving a hidden person get no `age_orders` entry; recording needs `RELATIONSHIP_WRITE` on both people (branch scope applies), visibility of both (404) and a recorded sibling relationship; deletion has the same checks | `test_age_order.py` (`test_dates_are_compared_only_as_the_viewer_may_see_them`, `test_hidden_people_are_never_compared`, `test_record_endpoint_rules`, `test_conflicting_birth_claims_never_force_an_answer`) |

## 4a. Security audit, 25 Sep 2026
An adversarial audit found 13 issues (3 High, 6 Medium, 4 Low). Each was proven with a failing test,
and all are fixed (SEC-12 closed in Phase 8 by email verification). `backend/tests/test_security_audit.py` keeps them as
regression tests.

| ID | Sev | Issue | Fix |
|---|---|---|---|
| SEC-1 | High | Branch-scoped members could pull outsiders into their branch (and so edit them), and could write to any household | Branch membership, founder and derive changes, and household writes are restricted to people and households inside the caller's scope |
| SEC-2 | High | A scoped invitation merged into an unscoped membership, widening the branch admin's grant | Scope conflict now returns 409. Scope is never widened silently. |
| SEC-3 | High | Self-set `linked_person_id` made the caller "self" for hidden people. The member list leaked hidden linked ids. | Only admins link members (never themselves). "Self" comes only from approved claims. Hidden linked ids are blanked. Branch admins see only their branch's emails. |
| SEC-4 | Med | Family view exposed a hidden partner through the union relationship | Union relationship is `null` when the partner is hidden |
| SEC-5 | Med | User-created source bound to a vault document could capture extracted vault values | Binding requires content access. Extraction uses a system-marked source at the document's privacy level. |
| SEC-6 | Med | PDF script filter bypass (name escapes); arbitrary bytes accepted as MP4/audio | Every reachable PDF object is walked (pypdf) for JS/AA/Launch/EmbeddedFile/XFA…. MP4/MP3/OGG/WAV/WebM get structural validation. |
| SEC-7 | Med | Citation delete checked only `source.write` | Needs write rights on the cited record, or authorship |
| SEC-8 | Low | Researchers could rename canonical places; place edits unaudited | Person/property writers only. Create and update audited. |
| SEC-9 | Med | Public family view exposed relationship notes and provenance | Public unions omit notes, legal status and provenance |
| SEC-10 | Low | Duplicate-upload 409 revealed hidden documents | Dedupe only against visible documents; the checksum index is no longer unique (migration 880d1a5976ec) |
| SEC-11 | Med | Erasure left GEDCOM extensions, proposals, links, relationship notes and claim/link fields | All cleared by erasure |
| SEC-12 | Low | Registration enumerates accounts | Fixed in Phase 8: generic `202` + email verification; existing owners get a notice email (T19) |
| SEC-13 | Low | Reading vault-derived extraction proposals was not audited | `document.proposals_viewed` audited |

Noted but not changed: login/register are exempt from CSRF, so an attacker could sign a victim into
the attacker's account. The impact is limited to the victim acting in the attacker's own empty account.
SameSite=Lax cookies apply.

## 5. Residual risks and deferred controls
- **Heritage visualization milestone (Oct 2026).** The SMS (Twilio) and WhatsApp (Twilio, Meta
  Cloud API) adapters are written against the providers' public APIs but have **not been exercised
  against the live services**; they stay disabled until credentials, DLT registration and template
  approval exist. A downloaded video or image leaves the platform's control (it shows what the
  requester could see when it was made). Render artifacts and delivery history have no automatic
  retention period yet. Remotion's licence must be checked before enabling renders in production.
- **Row-level security** covers tree-scoped tables only. Identity and control tables (`tree`,
  memberships, invitations, users, sessions, auth tokens, audit) rely on the service layer. The
  barrier is lost if a deployment connects the app as the table owner or a superuser (ADR-0002 §7).
- **DAST: executed (1 Oct 2026); first GitHub run still pending.** `.github/workflows/dast.yml`
  runs weekly (Mon 04:23 UTC) and on `workflow_dispatch`, never on pull requests. What it does:
  - starts Postgres 16 and Redis, migrates and seeds the demo tree as the owner;
  - serves the SPA with the **production nginx image**, then runs uvicorn as the non-owner
    `vanshavali_app` role (RLS in force) with the production proxy flags, trusting
    `X-Forwarded-For` only from that nginx container's exact address;
  - probes that a spoofed `X-Forwarded-For` is not recorded as the client IP (threat T30);
  - runs the ZAP baseline (passive, AJAX spider) and the ZAP API scan (active, from
    `/api/v1/openapi.json`) with the demo user's session and **real demo-tree IDs** fed to ZAP's
    form handler (`dast-ids.prop`). With placeholder path IDs, 99% of requests stopped at UUID
    validation and never reached the data paths. No CSRF header is sent, so the active scan
    covers authenticated reads but cannot mutate data; unsafe methods and BOLA stay covered by the
    authz test suite.

  **Executed** in the Cloud sandbox with the same steps, the same `zaproxy/zap-stable` image and
  the same `.zap/rules.tsv` (details in `docs/release/production-readiness.md`):
  - first run: baseline 0 FAIL, 4 WARN; API scan 0 FAIL, 3 WARN, 111 PASS. No injection, XSS,
    traversal or file-inclusion finding in 166 endpoints.
  - fixed from it: client-IP spoofing via `X-Forwarded-For` (T30, Medium); the nginx version in
    `Server`; third-party Google Fonts (no SRI possible, visitor IPs sent to Google), now
    self-hosted; CSP `style-src 'unsafe-inline'`, now `'self'`-only (0 violations in 24 browser page
    loads).
  - the ID-aware API scan then found a NUL byte in a query filter turning into an unhandled 500
    (psycopg `DataError`). Input the database cannot store is now a structured 422
    (`test_input_robustness.py`).
  - after the fixes: **baseline 0 FAIL / 0 WARN / 60 PASS; ID-aware API scan 0 FAIL / 0 WARN /
    113 PASS, 0 server errors** (reports in `docs/release/evidence/dast-2026-10-01/`).

  Rule policy (`.zap/rules.tsv`):
  - IGNOREs only where the justification holds in production (HSTS and `Secure` over CI's plain
    HTTP; informational SPA and caching notices);
  - two false positives scoped by URL (`OUTOFSCOPE`), so the rule stays live everywhere else: your
    own session IPs on `/auth/sessions`, and non-JSON content types outside `/api/` and for the
    zip archive export;
  - FAIL for clickjacking, nosniff, CSP (including `'unsafe-inline'`), server version, missing SRI,
    CORS, XSS, SQLi, injection and traversal;
  - COEP/CORP and the deliberately readable `vsh_csrf` cookie stay visible as WARN.

  Earlier, while building the workflow: nginx drops server-level `add_header` in any `location`
  that sets its own, so the SPA HTML and `/assets/` were served without CSP, X-Frame-Options and
  nosniff. Fixed with a shared `frontend/nginx-security-headers.conf` included per location.

  An independent penetration test is still outstanding: a public-launch blocker, scoped in
  `docs/security/pentest-scope.md`. CI also runs SAST (ruff `S` rules) and dependency audits.
- **Pilot deployment (ADR-0014, Oct 2026):**
  - The edge is Caddy (TLS, HSTS, body limits), the only published service. The backend trusts
    exactly its address. Production refuses unsafe proxy, CORS, URL, key and sender settings
    (T32).
  - Secrets live in mode-600 files on one VM; their handling and rotation are in
    `docs/security/secrets-management.md`.
  - **Residual risks:**
    - membership of the VM's `docker` group is root-equivalent;
    - the data keys cannot be rotated in place yet (no re-encryption tool);
    - a single VM is a single point of failure for availability, not for data.
- **Email verification pre-hijack:** someone can register a victim's address; the account stays
  unusable until the victim clicks the verification link. The email tells recipients to ignore it if
  they did not sign up, and a later reset replaces the password (ADR-0005).
- **Reset timing in sync job mode:** with `JOB_MODE=sync` and SMTP, a reset for a real account is
  slower (inline send). Production runs RQ, where every path only enqueues.
- **clamd availability:** scanning fails closed (uploads rejected while clamd is down), which trades
  availability for safety.
- **Watermarking of downloaded documents:** DEFERRED.
