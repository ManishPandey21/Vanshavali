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
| T20 | S / E | Emailed token theft or replay (verification, password reset) | 256-bit tokens, SHA-256 at rest, single use, 48 h / 1 h expiry, newer token kills older, password change kills reset links, reset revokes every session. Tokens are never audited and are redacted from console mail logs outside development. Links contain no third-party resources (no referrer leak) and the API sends `Referrer-Policy: no-referrer`. | `test_email_auth.py` |

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
- **Row-level security** covers tree-scoped tables only. Identity and control tables (`tree`,
  memberships, invitations, users, sessions, auth tokens, audit) rely on the service layer. The
  barrier is lost if a deployment connects the app as the table owner or a superuser (ADR-0002 §7).
- **DAST:** IMPLEMENTED, NOT YET EXECUTED. `.github/workflows/dast.yml` runs weekly (Mon 04:23 UTC)
  and on `workflow_dispatch`, never on pull requests, because a live scan is slow and flakier than
  unit tests. What the workflow does:
  - starts Postgres 16 and Redis services, then migrates and seeds the demo tree as the owner;
  - runs uvicorn as the non-owner `vanshavali_app` role, so RLS is in force, and gates on
    `/api/v1/health/ready`. `VSH_METRICS_TOKEN` is unset, so `/api/v1/metrics` answers 404;
  - serves the SPA with the **production nginx image** (`frontend/Dockerfile`), so the headers
    scanned are the real ones;
  - runs the ZAP baseline (passive, with AJAX spider) against the SPA;
  - runs the ZAP API scan (active) from `/api/v1/openapi.json`, with the demo user's session
    cookie (`ZAP_AUTH_HEADER`).

  No CSRF header is supplied, so the active scan covers authenticated reads but cannot mutate data.
  Unsafe methods and cross-tree/BOLA cases stay covered by the authz test suite. Rule policy is in
  `.zap/rules.tsv`:
  - it holds only IGNOREs that stay true in production (HSTS and `Secure` over CI's plain HTTP;
    informational SPA/caching notices);
  - clickjacking, nosniff, CSP, CORS, XSS, SQLi, injection and traversal alerts are escalated to
    FAIL;
  - known weaknesses (CSP `style-src 'unsafe-inline'`, COEP/CORP, the deliberately readable
    `vsh_csrf` cookie) stay visible as WARN.

  The workflow YAML passes `actionlint` (with shellcheck), but the workflow has **not run** yet,
  because this sandbox has no Docker daemon. Its first run may need rule tuning, and any change to
  the rules must keep a written justification.

  While building it, a real gap was fixed: nginx drops server-level `add_header` in any `location`
  that sets its own, so the SPA HTML (`/`) and `/assets/` were served **without** CSP,
  X-Frame-Options and nosniff. The fix is a shared `frontend/nginx-security-headers.conf` included
  per location, verified locally with nginx 1.24 and curl.

  A scheduled external penetration test is still DEFERRED. CI also runs SAST (ruff `S` rules) and
  dependency audits.
- **Email verification pre-hijack:** someone can register a victim's address; the account stays
  unusable until the victim clicks the verification link. The email tells recipients to ignore it if
  they did not sign up, and a later reset replaces the password (ADR-0005).
- **Reset timing in sync job mode:** with `JOB_MODE=sync` and SMTP, a reset for a real account is
  slower (inline send). Production runs RQ, where every path only enqueues.
- **clamd availability:** scanning fails closed (uploads rejected while clamd is down), which trades
  availability for safety.
- **Watermarking of downloaded documents:** DEFERRED.
