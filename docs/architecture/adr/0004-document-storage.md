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
7. **Retention:** soft delete (`deleted_at`) plus a restore endpoint. Purging after the retention
   period is **DEFERRED** to Phase 8.

## Consequences
Because the API serves bytes after decryption, S3 presigned URLs can't hand files out directly.
Download throughput scales with API replicas, which is acceptable for family archives. A
streaming proxy keeps memory bounded.
