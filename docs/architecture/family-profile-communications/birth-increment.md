# First birth-editing increment

Scope: initial A1/A2 slice under the staged legacy-access decision in ADR-0031 §11.
This is not completion of the full family-profile programme or strict privacy migration.

- Reuses open PR #74 (`8b2c9f6`) for inline birth/death entry, its en/hi labels and initial tests.
  Existing birth claims now have separate date, time and birthplace actions. Loading/missing
  events have visible recovery; a new event remains stable through the save/refetch cycle.
- Each focused save sends only its field group plus the loaded event revision. The revision stays bound to the draft across background refreshes. Server-side
  visibility checks protect direct birth-event writes, alongside existing person permissions.
  Authorized legacy administrators retain access. Proposals still require a separate reviewer
  who can see the changes; rebasing uses the proposal's freshly locked base revisions. Approval
  refreshes cached records after acquiring locks so a concurrent edit cannot escape that check.
- Times start with no assumed zone. Optional recorded seconds and UTC offset are preserved.
  Historical/partial dates and manually recorded Indic place text use existing editors.
- Date edits recompute personal reminders as their recipients, pause incomplete dates and
  cancel queued old-date occurrences transactionally. Scheduler, edit and delivery take the
  event lock first. Subscription/preference writers share that ordering and serialize per member
  so a new subscription cannot miss a simultaneous preference change. Still-valid queued
  occurrences survive year-only corrections; the ordinary grace window is reconsidered on edits.
  An unsent cancelled occurrence can be re-armed if its date becomes valid
  again; a previously attempted/sent occurrence cannot be resent by toggling dates.
- API types are regenerated. No schema migration, new provider, subscription or live send.

Not in this slice: strict field-controller policies/conversion, withheld state, explicit 12/24
format selector, claim selector, new citation controls, profile reminder affordances, address
schema/reuse/consent release, contacts and new channels. Existing event/source/review screens
remain available. Backend date editing and browser editing are being verified separately.

## Verification

On 12 November 2026, using the local PostgreSQL application role with RLS enabled:

- Full backend run at the initial implementation: **818 passed, 1 skipped** (optional real
  Remotion renderer). Follow-up scheduling, approval, privacy and threat-ID regressions on the
  revised candidate: **60 passed**. The final proposal-metadata refinement's rebase/approval
  regression passed separately. No backend failure remains.
- Backend Ruff lint/format and mypy: pass. OpenAPI and frontend API types regenerated.
- Full frontend: **230 passed** across 45 files; lint, TypeScript and production build pass.
  Vite retains the existing bundle-size advisory.
- Focused real-stack birth editing: **5 passed**, including create/edit/reload, cancellation,
  seconds/offset with unknown zone, manually recorded Hindi birthplace, and desktop/mobile axe.
- Full browser suite: **50 passed, 1 failed** on a heading-readiness race in the accessibility
  harness. The harness now waits for the route's required h1 before scanning; English/Hindi
  signed-in-page rerun: **2 passed**. The failed English audit and the Hindi counterpart both
  pass with the corrected readiness check; no unresolved browser failures remain.
- Two isolated standards/specification reviews: no remaining actionable findings after recheck
  through code commit `b9f2bd2`. See [review evidence](birth-review.md).

Negative/concurrency evidence includes hidden-field denial, preserved legacy administrator access,
cross-tree denial, stale forms across background refreshes, earlier-date rescheduling, incomplete
pause/resume, queued cancellation, same-day year corrections, post-fire date toggling without
repeat sends, both edit/delivery lock orders, scheduling-writer races, and proposal rebase plus
approval racing an edit. Test deliveries use file/mock transports; no real messages were sent.

The development API was restarted with source reload enabled and verified to expose the new
revision precondition; API readiness and frontend both return HTTP 200. Claude-only factory
configuration targets `feature/profile-birth-editing`; its dry run selects no tickets.

Review base: `c8fe982b534f893336575e31575ef457bd1451bf`. Coordinator implementation, not a
Code Factory ticket run; no EGM execution receipt is claimed. No merge or deployment authorized.
