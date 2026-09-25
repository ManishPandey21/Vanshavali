# ADR-0004: Document pipeline; OCR/AI output is only ever a proposal

- Status: Proposed
- Date: 2026-09-25

## Decision
Pipeline: **Original File → Validation → Malware Scan → Immutable Storage → OCR → Extraction →
ExtractionProposal → Human Review → Confirmed Fact → Citation/Provenance.**

1. *Validation:* check the file against an allowlist of types by magic bytes (PDF, JPEG, PNG, TIFF,
   HEIC), with a size cap, page cap and image-pixel cap. Reject encrypted or scripted PDFs, or send
   them to quarantine.
2. *Scan:* the file sits in a quarantine prefix and nothing downstream reads it until the scan is
   clean.
3. *Storage:* a private bucket with a content-addressed key (`sha256`) and object lock/versioning.
   The original bytes are never modified. Derived files (thumbnails, OCR text) are stored separately.
4. *OCR/extraction* runs in an isolated worker with no DB write access to canonical tables. It can
   only insert `extraction_proposal` rows.
5. *Review:* a user with editor rights (or higher) accepts, edits or rejects each field. Accepting
   writes the fact in one transaction together with a Citation to the document's Source, and the
   audit log records who accepted it and the original proposal.
6. *Download:* the API authorises the request, then issues a short-lived (≤5 min), single-object
   signed URL with `Content-Disposition: attachment`. Buckets are never public.

## Consequences
Any AI model used for extraction is recorded (provider, model, version) on each proposal. Sending
documents to an external AI provider needs explicit consent per tree (Q7).
