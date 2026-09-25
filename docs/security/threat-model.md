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
| T1 | I / E | **IDOR/BOLA**, cross-tree access to any resource | Tree context resolves membership, and non-members get **404**. Every lookup uses `tree_id` (`lookup.get_in_tree`). Composite `(tree_id, id)` FKs make cross-tree references impossible in the DB. | `test_route_isolation.py` (every `/trees/{tree_id}` route, stranger and anonymous), `test_privacy.py::test_cross_tree_access_is_404`, `test_heritage_family.py::test_citation_cannot_target_other_tree` |
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
| T14 | D | Deep or wide traversal, huge uploads, pathological GEDCOM | Depth caps (≤25), node cap (500), upload size cap, parser record caps, statement timeouts (Phase 8) | `test_genealogy.py`, `test_gedcom.py` |
| T15 | T | Tampering with stored originals | Write-once keys (local `O_EXCL`, S3 `If-None-Match`). SHA-256 recorded. AES-GCM authentication detects modified ciphertext. | `test_documents.py` |
| T16 | I | Key compromise / bucket leak | Separate STANDARD and VAULT keys. Keys only from a secret manager (production config refuses dev keys). | `core/config.py` validator |
| T17 | S / T | Forged property shares presented as title | `legal_notice` on every property response. The documented-share invariant is ≤ 1. Status distinguishes asserted, documented and disputed. | `test_property.py` |
| T18 | I | Analytics/log leakage | No analytics SDK. Audit `details` hold field names only. Documents are never logged. | code review |

## 5. Residual risks and deferred controls
- **Row-level security** as a second isolation barrier: DEFERRED (Phase 8). Current controls: the
  service layer plus composite FKs plus route-isolation tests.
- **DAST** and a scheduled penetration test: DEFERRED (Phase 8). CI runs SAST (ruff `S` rules) and
  dependency audits.
- **Password reset and email verification:** deferred until an email provider exists. Until then,
  admins re-invite.
- **clamd availability:** scanning fails closed (uploads rejected while clamd is down), which trades
  availability for safety.
- **Watermarking of downloaded documents:** DEFERRED.
