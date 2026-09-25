# ADR-0004: Document storage, scanning and encryption

- Status: Accepted · Date: 2026-09-25

## Decision
1. **Pipeline:** receive the upload (streamed, size-capped) → sniff the type from magic bytes against
   an allowlist (PDF, JPEG, PNG, HEIC/HEIF, TIFF, WebP, MP3/M4A/WAV/OGG, MP4/WebM) → check
   decompression limits (Pillow `MAX_IMAGE_PIXELS`, PDF page cap, and rejection of encrypted PDFs or
   PDFs containing JavaScript) → compute SHA-256 → **malware scan** → encrypt → store under an
   immutable key → record the Document row → queue preview and OCR jobs.
2. **Scanner interface.** Production uses `ClamdScanner` (clamd INSTREAM). `EicarTestScanner` is
   for tests and dev only, and config validation refuses it when `ENV=production`. Infected files
   are rejected with 422 and never stored.
3. **Storage interface** `ObjectStore.put_immutable/get/presign`: `S3ObjectStore` (MinIO/S3) and
   `LocalObjectStore` (dev/tests). Keys are
   `{class}/{tree_id}/{sha256[:2]}/{document_id}/original`, and objects are never overwritten.
4. **Encryption at rest:** app-level AES-256-GCM envelope encryption with a separate key per storage
   class (`STANDARD_DATA_KEY`, `VAULT_DATA_KEY`, from the secret manager). This is independent of
   the provider. In production, S3 SSE-KMS and bucket versioning/object-lock are added on top.
5. **VAULT class** (automatic for the categories birth certificate, death certificate, marriage
   certificate, will, deeds, land and revenue records, identity documents, court orders, Kundli)
   defaults to `PRIVATE_TREE_ADMINS` and needs an explicit download permission.
6. **Downloads:** after authorisation the API issues a signed URL that lasts ≤300 s: an HMAC token
   bound to (document, user, variant, expiry) that the API serves decrypted, with
   `Content-Disposition: attachment`, `nosniff` and `Cache-Control: no-store`. Every issue is
   audited.
7. **Retention:** soft delete (`deleted_at`) plus a restore endpoint. After
   `VSH_DOCUMENT_PURGE_AFTER_DAYS` (default 30), the daily maintenance job
   (`python -m app.cli.maintenance purge-deleted-documents`) removes the document **permanently**:
   - It deletes the original and all derivatives, including every S3 version (`ObjectStore.purge`).
   - It deletes the row with its links, metadata history and extraction proposals.
   - References from sources, astrology profiles, consent records and import jobs become NULL.
   - It writes a `document.purged` audit event without the title.
   - Bucket object-lock retention must be shorter than the purge window, or purges fail and are
     retried on the next run.
   - `sweep-orphans` reports stored objects that no row references. It deletes them only with
     `--delete`, and never touches anything younger than 24 h or outside the app's key layout.
   - Both commands run tree by tree with the tree bound, so they work as the RLS-restricted role
     (`tests/test_retention.py`).

## Consequences
Because the API serves bytes after decryption, S3 presigned URLs can't hand files out directly.
Download throughput scales with API replicas, which is acceptable for family archives. A
streaming proxy keeps memory bounded.
