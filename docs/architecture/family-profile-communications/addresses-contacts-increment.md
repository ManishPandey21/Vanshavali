# Addresses and contacts increment

Date: 12 November 2026  
Branch: `feature/profile-addresses-contacts`  
Design: [ADR-0031](../adr/0031-family-profile-addresses-and-communications.md)

## Delivered in this increment

- Added encrypted, tree-scoped person address records with controlled purposes, explicit current/former
  state, one optional primary-current address, linked Place plus captured administrative labels,
  genealogical validity dates, withdrawal, optimistic revisions and idempotency keys.
- Address entry covers settlement, sub-district/tehsil/taluka, district/state, as-recorded gram
  panchayat and post office, and rejects content-free records. Postal code and exact postal details
  stay in the encrypted payload. Existing Sources can cite an address through the evidence model.
- Added encrypted before/after address history. Correction keeps one record; the move API atomically
  turns the selected record former and creates a new current record without closing other current
  residences. Repeated move requests return the same new address.
- Added typed encrypted person contacts for email, mobile, WhatsApp, Telegram, Instagram and legacy
  notes. Lists expose only masked hints; reveal is a separate authorized and audited action. Preferred
  contact is unique per person and kind. Preferred language is optional. “Same as mobile” is an
  explicit revision-bound copy; a later mobile change marks the WhatsApp copy for review rather than
  silently synchronizing. Profile contacts do not verify, subscribe or send anything.
- Converted legacy `residential_address` and `contact_info` values verbatim into encrypted records in
  migration `c8f4a2d7e901`, then cleared the plaintext columns. Old create/update clients write through
  to the encrypted records and old authorized reads receive a compatibility projection.
- Included the new records and encrypted history in RLS, erasure, audit events, generated OpenAPI
  types and the profile UI. The address form reuses the existing Place/LGD/PIN-capable picker and
  remains usable with manual or overseas text.
- Added complete en/hi profile controls for add/correct/move/remove, authorized address history,
  masked contact display and explicit reveal. Validated Telegram/Instagram handles expose only
  fixed-host HTTPS profile links. Collection/history APIs are cursor paginated.
- Serialized parent-person locks and partial unique indexes protect concurrent primary/preferred,
  idempotency and legacy compatibility writes. Revision reasons are encrypted; contact history stays
  masked instead of bypassing the audited explicit-reveal boundary.

## Verified boundary

Focused automated checks cover FP-C01, FP-C02, the core encrypted/legacy parts of FP-C04, FP-E01,
FP-E02 and route/privacy negatives from FP-X01. They prove encrypted payload/history storage,
revision conflicts, definite-date and move-interval validation, atomic/idempotent moves, multiple
current residences, preferred-contact uniqueness, concurrent create/legacy-write races, minimum
address identity, revision-bound WhatsApp copy warnings, syntax validation, fixed-host social links,
explicit reveal, same-tree privilege and cross-tree denial, erasure, pagination and clean migration
upgrade/check/downgrade.

This does **not** mark the whole B/C/E programme complete. Still open:

- strict field-controller conversion and encrypted review/proposal adapters from A0/C;
- split coarse current-city visibility from full postal visibility;
- reverse-PIN candidate and recorded-versus-reference mismatch UX beyond the existing place picker;
- browser E2E, 390 px/axe/manual screen-reader and native-Hindi review;
- backup/restore evidence for the new encrypted tables.

## Next planned increment

**D — reusable family/ancestral addresses.** Implement immutable shared address versions, explicit
link versus copy, source-owner consent before independently sharing a copy, privacy-ceiling and
erasure propagation, ancestral assertion/property associations, and the optional Smart Add branch
suggestion. Close the remaining C privacy/proposal gates before marking C complete.

After D, continue with F (invitation front door), G (reminder UX), then provider-readiness work H–J.
No live provider activation or deployment is implied by this increment.
