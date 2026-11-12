# Birth-editing slice review

Fixed base: `c8fe982b534f893336575e31575ef457bd1451bf`.
Initial candidate: `e502074b0cc49c316d401ec76e7701bcb7b9405b`.
Rechecked candidate: `166a1eb9bf3651068cd1b937e86f04d6dcf63455`.
Final narrow recheck: `b9f2bd2b4f335fdd0d08b41900b1f3a701dbe987` (both reviewers clear).

Two isolated reviewers followed the code-review skill. Scope was the initial A1/A2 slice in
[birth-increment.md](birth-increment.md), with staged legacy access explicitly retained. Future
address/contact/policy features were not represented as implemented or reviewed code.

## Standards

Initial findings:

1. The event revision was reactive while the edit draft was initialized once. A background
   refresh could authorize an old draft with a newer revision. Fixed by retaining the draft's
   original revision and covered by a component regression.
2. New subscriptions and preference/reminder updates did not use the date-edit anchor lock.
   They could overwrite a newly corrected schedule with an old-date schedule. Fixed by locking
   the member's scheduling operations, then events in UUID order, then dependent reminders.
   Tests hold real transactions open and prove both orderings, including a new subscription
   racing a preference update.

Recheck: **no remaining actionable standards findings**. The reviewer also checked the proposal
identity-map fix: cached records are refreshed after taking the revision lock, with a regression
that first failed by incorrectly accepting a stale proposal.

## Specification

Initial findings:

1. Draft/revision mismatch (same underlying defect as the standards finding).
2. Cancelling every pending delivery on any date PATCH discarded still-valid birthdays when
   only the year changed. A post-fire A→B→A edit could also miss re-arming an unsent occurrence.
   Fixed by preserving matching deliveries and reconsidering the ordinary scheduler grace
   window. Attempted/sent deliveries retain their unique identity and are never re-armed.

Recheck: **no remaining actionable specification findings**. The post-fire toggle and year
correction regressions cover the scheduling fix. Expressly deferred features remain deferred.

The final change excludes transport-only `expected_revision` from stored proposal fact patches;
proposal-owned base revisions still govern approval. Both reviewers confirmed their clear findings
still hold, and the rebase/approval regression verifies that the field is absent from review changes.

Both reviews were static source/test reviews; reviewers did not execute tests. Coordinator
execution results are recorded in the implementation note. No review authorizes merge,
deployment, live messaging, or a strict field-policy migration.
