# First birth-editing increment

Scope: initial A1/A2 slice under the staged legacy-access decision in ADR-0031 §11.
This is not completion of the full family-profile programme or strict privacy migration.

- Reuses open PR #74 (`8b2c9f6`) for inline birth/death entry, its en/hi labels and initial tests.
  Existing birth claims now have separate date, time and birthplace actions. Loading/missing
  events have visible recovery; a new event remains stable through the save/refetch cycle.
- Each focused save sends only its field group plus the loaded event revision. Server-side
  visibility checks protect direct birth-event writes, alongside existing person permissions.
  Authorized legacy administrators retain access. Proposals still require a separate reviewer
  who can see the changes; rebasing uses the proposal's freshly locked base revisions.
- Times start with no assumed zone. Optional recorded seconds and UTC offset are preserved.
  Historical/partial dates and manually recorded Indic place text use existing editors.
- Date edits recompute personal reminders as their recipients, pause incomplete dates and
  cancel queued old-date occurrences transactionally. Scheduler, edit and delivery take the
  event lock first. An unsent cancelled occurrence can be re-armed if its date becomes valid
  again; a previously attempted/sent occurrence cannot be resent by toggling dates.
- API types are regenerated. No schema migration, new provider, subscription or live send.

Not in this slice: strict field-controller policies/conversion, withheld state, explicit 12/24
format selector, claim selector, new citation controls, profile reminder affordances, address
schema/reuse/consent release, contacts and new channels. Existing event/source/review screens
remain available. Backend date editing and browser editing are being verified separately.

Validation in progress: full backend suite; full frontend lint/types/tests/build; real-stack
birth editing including manual Indic birthplace and seconds/offset, plus desktop/mobile axe.
Focused backend evidence: hidden-field denial, preserved legacy admin access, stale revision,
earlier-date reschedule, partial-date pause/resume, queued cancellation, both real-database
edit/delivery lock orders, and stale-proposal rebase/approval. All sends use the test file backend.

Review base: `c8fe982b534f893336575e31575ef457bd1451bf`. Coordinator implementation, not a
Code Factory ticket run; no EGM execution receipt is claimed. No merge or deployment authorized.
