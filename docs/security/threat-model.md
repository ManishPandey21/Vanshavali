# Threat model

Status: baseline written at project start (STRIDE). Revisit whenever auth, authz, sharing,
uploads, downloads, exports or admin features change.

## 1. Assets
Living people's and children's personal data; caste and religious data; Kundli and birth details;
property documents and land parcels (fraud and litigation value); account credentials; the
integrity of the tree itself (forged lineage used to claim property).

## 2. Actors and roles
Anonymous visitor · share-link holder · tree `viewer` · `contributor` (proposes edits) · `editor` ·
`property_manager` · `owner` · platform admin · OCR worker (a service) · malicious insider (a family
member acting in bad faith).

## 3. Trust boundaries
Browser ↔ API · API ↔ Postgres (RLS) · API ↔ object storage (signed URLs) · queue ↔ OCR worker ·
worker ↔ any external AI provider.

## 4. Threats and required controls

| # | STRIDE | Threat | Control | Required negative test |
|---|---|---|---|---|
| T1 | Elevation / Info disclosure | **IDOR/BOLA:** requesting `/persons/{id}` or `/documents/{id}` from another tree | Every lookup is `WHERE tree_id = :authorised AND id = :id`, plus RLS. Unknown and forbidden both return **404**. | A user in tree A requests every resource type in tree B and gets 404. RLS test runs as the app role with the service filter bypassed. |
| T2 | Elevation | A viewer or contributor edits directly through the API | A role check on each handler, deny by default, one central policy table | Each mutating endpoint is called by each role below the one it requires and returns 403 (UI flow 4 in the README) |
| T3 | Elevation | A member gives themselves or someone else a higher role | Only `owner` can change roles. The last owner can't be demoted. | An editor tries to promote themselves, then demote the owner. Both are denied. |
| T4 | Info disclosure | A living person or minor leaks through the public view, search, export, share link or tree image | Privacy serialisers (privacy-model §3), plus a living and minor check at render time | A fixture with a living adult and a minor, checked against the public tree, search, GEDCOM public export and share link. Their names must be absent. |
| T5 | Info disclosure | A signed URL is reused, lasts too long or is guessable | Signed only after authorisation, TTL ≤ 5 min, single object, private bucket, keys that can't be guessed | An expired URL gets 403. A URL for doc X can't read doc Y. Anonymous bucket listing is denied. |
| T6 | Tampering / Elevation | Malicious upload: polyglot file, PDF with JS, zip bomb, SVG with XSS, huge image | ADR-0004 validation, quarantine and scan. No SVG/HTML uploads. `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`. | EICAR, a mislabelled mime type, an oversize file and a PDF with JS are each rejected or quarantined. |
| T7 | Tampering | OCR/AI output (or prompt injection inside a document) silently changes canonical data | The worker can only insert proposals. Accepting requires a human. | The worker's DB role can't write to `person` or `relationship`. A proposal alone changes nothing. |
| T8 | Repudiation | A disputed lineage or property edit | An append-only audit log (who, when, before and after) for canonical and property tables | Every mutation writes one audit row, and the audit table rejects UPDATE and DELETE. |
| T9 | Spoofing | Credential stuffing, stolen session | Argon2id, rate limits, optional TOTP, httpOnly SameSite cookies, CSRF tokens, session rotation | Login lockout test, and a CSRF-less POST is rejected. |
| T10 | Info disclosure | Enumerating people via sequential IDs or search | UUIDv7 IDs, authenticated search, rate limits | — |
| T11 | Elevation | A platform admin reads tree content | Admin tools see metadata only. Reading content requires break-glass access that is audited. | An admin endpoint response contains no person fields. |
| T12 | Info disclosure | Export used to take everything out at once | Exports are role-scoped, rate-limited and audited, and download links expire | A viewer's export contains no S2 or S3 data. |
| T13 | DoS | A deep recursive query or a huge tree render | Depth limits, pagination, statement timeouts | Ancestors endpoint with depth > max returns 400. |

## 5. Current prototype exposure
There is no backend, so the only real risk today is shipping sample data with realistic personal
details to a public host. `sampleData.ts` holds fictional people only, and must stay that way.
