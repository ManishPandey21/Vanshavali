# Reusable family and ancestral addresses — increment D

Status: **implemented and locally verified on `feature/reusable-family-addresses`** (12 November
2026). This record distinguishes the delivered boundary from later release gates; it is not a merge
or deployment claim.

## Completed

- Added tree-scoped `family_address`, immutable `family_address_version`, cycle-safe
  `family_address_version_source`, full-chain `family_address_version_ancestor` and explicit
  `family_address_release_consent` records with RLS, composite foreign keys, bounded metadata,
  encrypted postal snapshots and a reversible Alembic migration.
- Added authorized family-address list/detail/create, immutable correction, filtered affected-link
  preview, retirement, membership-bound selected-reader grants and cursor-paginated source search.
- Added person-address **link** and **copy** flows. Links pin a version and require explicit adoption
  of later corrections. Copies are independently editable but recheck their source policy at commit
  and read; source retirement, controller removal and grant revocation hide derivatives.
- Added an exact added-reader preview and independent-sharing release consent bound to each source
  version, destination, controller membership, audience/branch, purpose, notice version and
  timestamp. Every current controller in the copy chain must consent; withdrawal reapplies all
  original ceilings.
- Source-person erasure, branch deletion and ancestral-assertion removal now blank and withdraw
  every downstream person/family snapshot and history before provenance FKs can be cleared,
  retaining only fail-closed tombstones.
- Ordinary source withdrawal, family retirement and controller-membership loss are revalidated on
  every read, including after a release. Adding a selected-member grant withdraws the old chain
  consents so the widened audience must be previewed and approved again.
- Reused the existing canonical `ancestral_village` assertion and Place instead of creating a
  parallel ancestry fact. As-recorded/historical labels survive reuse; no address flow infers an
  assertion, residence or property interest. An ancestral-derived family address remains under
  the assertion's live privacy/erasure ceiling, including after correction.
- The shared PlacePicker offers matching existing tree places while retaining the typed historic
  spelling as recorded; it never links a match automatically.
- Added the profile source picker with authorized Recent, Family, Branch, Ancestral and My-address
  groups, server-side search, link/copy explanation, source-policy notice, reuse badges and explicit
  linked version adoption. Recents retain identifiers per membership in audit history and are
  reauthorized on every read; My-address sources are absent unless the membership has a linked profile.
- Smart Add now offers authorized ancestral villages from the anchor's recorded branches with
  explicit Use recorded / Choose another / Enter new / Leave unknown choices. Confirmation creates
  only a person ancestral-village assertion; it never fills birthplace or residence.
- Regenerated OpenAPI/TypeScript contracts and added English/Hindi UI keys.

## Verification evidence

- `backend/tests/test_family_addresses.py`: encrypted snapshots; link/copy independence; immutable
  pinning; correction preview/adoption; retirement; source filtering; cross-tree rejection;
  canonical ancestral reuse; selected-member grant/revocation; controller-membership removal;
  version/audience consent and withdrawal; multi-controller copy-chain consent/preview; source
  person/branch and ancestral-assertion erasure propagation; ordinary source withdrawal; released-source
  retirement; selected-reader widening and source-grant invalidation; encrypted correction reasons;
  assertion ceilings retained across correction; membership-scoped reauthorized recents.
- `backend/tests/test_smart_add.py`: authorized branch-village offer, explicit recorded acceptance,
  unknown choice and proof that neither birthplace nor residence is created.
- `backend/tests/test_migrations.py::test_upgrade_check_downgrade_roundtrip`: empty-database upgrade,
  ORM parity, RLS schema and clean downgrade.
- `backend/tests/test_family_address_downgrade_guard.py`: populated rollback is refused before it
  can delete ciphertext/history/grants or forget a source-policy ceiling.
- `frontend/src/pages/tree/person/profile.test.tsx` and `SmartAddDialog.test.tsx`: searchable grouped
  source picker, copy choice, linked-address immutability, explicit version adoption and explicit
  ancestral-village confirmation with its no-birthplace/residence notice.
- `e2e/tests/reusable-addresses.spec.ts`: real SPA/API source picker, link, independent copy,
  correction notification and explicit adoption while the copy remains pinned.
- Backend Ruff, formatting, MyPy, focused API tests and the complete backend suite pass; the
  clean-schema migration drift and downgrade/upgrade round-trip pass. Frontend typecheck, lint, all
  235 component tests, production build and the real-stack Playwright flow pass.

## Explicitly not completed by D

- A0 strict controller-only conversion for all legacy person fields, and the remaining C
  proposal/export/backup-restore hardening, remain release gates.
- Full PIN reverse-candidate/mismatch UX and a family address administration screen remain B/D
  follow-up refinements; the profile reuse/adoption and Smart Add ancestral-village paths are delivered.
- Native-Hindi review, screen-reader review, deployment approval and real-data validation are human
  release gates, not inferred from automated tests.
- No branch merge, deployment or external messaging action is part of this increment.

## Next

The next planned product increment is **F — invitation front door**. After F, proceed to G reminder
UX and H–J provider-readiness evaluations while retaining the open A0/B/C release gates above.
