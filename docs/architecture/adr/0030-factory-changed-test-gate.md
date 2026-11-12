# ADR-0030: Factory changed-test gate inside the builder command

- Status: **Proposed** · Date: 2026-11-11 · Revised 2026-11-12 for toolkit 0.5.0
- Amends: [ADR-0029](0029-agent-ticket-factory.md) (agent ticket factory, toolkit **0.5.0** per its
  Amendment 1). Runbook: [code-factory.md](../../operations/code-factory.md).

## Context

The first live ticket, U02-VITALS-EDIT-B, used two of its three attempts without reaching review:

- Attempt 1: the builder could not run tests (no dependencies), guessed a heading ("Vitals" for
  "Life details"), and the new component test failed in cold verification.
- Attempt 2 (dependencies now provisioned): the builder ran its component tests red→green but
  **not its new Playwright spec**, saying it "needs the full backend and database stack". The spec
  looked for the same wrong heading and failed in both cold checkouts. Run in the builder's own
  worktree with its allowed command, the spec reproduces the failure in 14 s.

The defect took 30+ minutes of cold verification to find, and an attempt to pay for. Nothing
between the builder and cold verification ran the tests the builder had just written.

This ADR was first written against a locally patched toolkit 0.3.4 that also pinned models and
efforts, carried attempt history across replacement tickets and did not charge infrastructure
refusals. Toolkit 0.5.0 (ADR-0029 Amendment 1) now provides strict model/effort routing, served-model
checks, routing evidence and `supersedes` attempt history itself, so those parts were dropped along
with the 0.3.4 patch. What remains is the gate, which 0.5.0 does not have.

## Decision

1. **Changed-test gate** (`ops/factory/changed_test_gate.py`, run by `bootstrap_builder.py --gate`,
   which every builder command already starts through): after the agent exits and before the
   controller commits, the wrapper runs every test file the builder created or changed, and every
   test file the ticket declares, in a **fresh controller-provisioned worktree** holding exactly the
   builder's changes, never the builder's tree (so ignored files it left cannot decide the result).
   One file per run, with runners that never install (vitest, targeted Playwright with its own
   backend/SPA/database on private ports, pytest with a private database), with JUnit evidence.
   Pass = exit 0, ≥ 1 test from that file, no failure, error or skip. Manifest, harness,
   tool-config and existing-test edits, and agent configuration the builder wrote, are refused
   before anything runs. A declared test that was not written, or a test file with no trusted
   runner, fails. The gate may not change the candidate (content-hash check). The builder's prompt
   says the gate exists and how to run each kind of test itself.

2. **Repair rounds inside the attempt.** A gate failure goes back to the builder with the
   controller's own output for at most `--repair-rounds` (default 1, max 2) more turns, with the
   same command (model and effort), inside the same builder command; then the builder command
   fails and 0.5.0 blocks the ticket. The builder command's time limit is 5400 s (was 3600) so a
   repair round fits; the wrapper stops starting rounds 300 s before it.

3. **Host checks before the agent:** free disk space (≥ 5 GB) and the Node major version CI uses (22).
   A failing host check, a refused gate module, or a model/effort the bridge refuses (0.5.0 exits 2
   and records `routing_refused` in `<result>.routing.json`) exit 75 so the log shows a host or
   account problem, not the work. **0.5.0 still charges the attempt** for any failed builder
   command; the code only makes the cause visible.

4. **Evidence:** `changed-tests.json` and per-file logs in the ticket's log directory; round 0
   writes the `builder-result.json` and routing evidence that 0.5.0 verifies, and repair rounds write
   `builder-result.repair-N.*` beside them. `ops/factory/routing_report.py` joins the ledger
   (`<git-common-dir>/infra-factory`), routing evidence, gate evidence, cold results and the
   standards/spec reviews into per-model/effort outcomes and cost.

## Consequences

- A builder's claim that tests pass is replaced by controller-run evidence; U02-style defects stop
  in about a minute at the gate instead of after cold verification (measured on 0.3.4: the real gate
  rejects the U02 attempt-2 candidate in ~30 s, Playwright 1 failure, vitest 5 passed).
- Cold verification and every 0.5.0 review lens are unchanged. The gate adds time to every builder
  run that touches tests (one targeted Playwright run starts the full stack, ~15–40 s).
- A repair round costs one more builder turn at the builder's model and effort, but no attempt.
  `--repair-rounds 0` restores block-on-first-failure. 0.5.0's own `factory.py repair` (after review
  or CI) is separate and does use the attempt budget.
- Host and account refusals now cost an attempt (they did not under 0.3.4). Fix the host before
  retrying; the exit code and `changed-tests.json` say which it was.
- The gate depends on 0.5.0 appending the ticket JSON to the builder prompt and writing
  `<result>.routing.json`; a toolkit upgrade must keep both or update the gate in the same PR.

## Alternatives considered

- **Keep the patched 0.3.4 toolkit.** Rejected once 0.5.0 landed: it would pin two toolkits and two
  routing implementations, and 0.5.0 covers routing, served-model checks and attempt history.
- **Patch 0.5.0 to run the gate in the controller.** Rejected: the builder command is already a
  repository-owned wrapper, so the gate needs no toolkit fork.
- **Fail the attempt on the first gate failure (no repair round).** Kept available
  (`--repair-rounds 0`), not the default: the builder never saw its own failure in either U02
  attempt, so one bounded feedback turn is the cheapest fix and costs no attempt budget.
- **Trusting the builder transcript to show tests ran.** Rejected: a transcript is the builder's
  own account. The gate executes the tests itself.
