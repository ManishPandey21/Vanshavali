# ADR-0030: Factory model/effort routing and the changed-test gate

- Status: **Proposed** · Date: 2026-11-11
- Amends: [ADR-0029](0029-agent-ticket-factory.md) (agent ticket factory). Toolkit: Infra Code
  Factory **0.3.4** = the reviewed 0.3.3 archive + `ops/factory/toolkit/infra-code-factory-0.3.3-to-0.3.4.patch`.
- Runbook: [code-factory.md](../../operations/code-factory.md).

## Context

The first live ticket, U02-VITALS-EDIT-B, used two of its three attempts without reaching review:

- Attempt 1: the builder could not run tests (no dependencies), guessed a heading ("Vitals" for
  "Life details"), and the new component test failed in cold verification.
- Attempt 2 (dependencies now provisioned): the builder ran its component tests red→green but
  **not its new Playwright spec**, saying it "needs the full backend and database stack". The spec
  looked for the same wrong heading and failed in both cold checkouts. Run in the builder's own
  worktree with its allowed command, the spec reproduces the failure in 14 s.

An audit of 0.3.3 against the installed Claude Code CLI (2.1.322) found the model layer unpinned:

- Roles used aliases (`sonnet`, `opus`), which `ANTHROPIC_DEFAULT_*_MODEL` / `ANTHROPIC_MODEL` can
  remap, and no effort was ever passed. Reviewers run in a scrubbed environment, so an environment
  variable could not have set their effort either.
- The CLI lets `CLAUDE_CODE_EFFORT_LEVEL` override `--effort`; a settings `maxEffortLevel` clamps it
  silently; **an unknown effort (`--effort ultra`) is accepted with exit 0**; `--fallback-model` and
  overload fallback can switch models; the effective effort is reported nowhere.
- Builders were chosen by layer (`frontend`/`backend`), not by how hard or risky a ticket is.
- Nothing stopped a blocked ticket being re-added under a new id with a fresh three-attempt budget
  (the toolkit's own message suggested exactly that).

Fable 5.2, Opus 5.5 and Sonnet 5.5 all answered at every effort level on this host, and each run
reported only the requested model in `modelUsage`; a nonexistent model fails with `is_error`.

## Decision

1. **Pinned model + explicit effort per role** (`configure_factory.py` `ROUTES`, overridable with
   `--route ROLE=PROVIDER:MODEL:EFFORT`):

   | Role | Model / effort |
   |---|---|
   | `builder_routine` (default `complexity`) | `claude-sonnet-5-5` / medium |
   | `builder_complex` (`complexity: complex`) | `claude-opus-5-5` / high |
   | `builder_critical` (`role: critical`) | `claude-opus-5-5` / high |
   | `reviewer_standards`, `reviewer_spec` | `claude-opus-5-5` / high |
   | `reviewer_standards_critical` | `claude-opus-5-5` / high |
   | `reviewer_spec_critical` (exceptional-risk escalation) | `claude-fable-5-2` / high |

   Coordinator (Opus 5.5 / medium), architecture supervisor (Fable 5.2 / high) and read-only
   classification/summary (Sonnet 5.5 / low) are desktop-session roles the factory does not launch;
   the runbook states them as guidance. Fable is not used for polling, summaries or ordinary coding
   unless selected explicitly. `--providers mixed` keeps Codex for routine builds and the standards
   lens (`-c model_reasoning_effort=…`, low/medium/high).

2. **Strict routing in the bridge** (toolkit 0.3.4, `--strict-routing`): full model ids only;
   effort validated, then passed as both `--effort` and `CLAUDE_CODE_EFFORT_LEVEL`; model-remapping
   variables removed; `CLAUDE_CODE_NO_MODEL_FALLBACK=1` and never `--fallback-model`; a settings
   `maxEffortLevel` below the request refuses the run; the result is refused unless the requested
   model served it. Every run writes `<result>.routing.json` (requested vs. served model, effort
   controls, tokens, cost, denied tool names, outcome; never credentials or environment values),
   builders keep their `stream-json` transcript, and the factory blocks a strict command that left
   no successful routing evidence. `configure_factory.py --apply` probes every distinct
   provider/model/effort through the real bridge first and writes nothing if one fails.

3. **Risk/complexity routing** (toolkit 0.3.4): ticket field `complexity` (`routine` | `complex`)
   plus `role: critical` select the builder; critical tickets may escalate reviewers. Suites are
   still selected by `paths`, so routing never changes what is verified. Older configurations keep
   routing by `role`.

4. **Changed-test gate** (`ops/factory/changed_test_gate.py`, run by `bootstrap_builder.py --gate`):
   after the builder exits and before the controller commits, the controller runs every test file
   the builder created or changed, and every test file the ticket declares, in the builder's
   changes — in a **fresh controller-provisioned worktree** holding exactly those changes, never the
   builder's tree (so ignored files it left cannot decide the result), one file per run with
   runners that never install (vitest, targeted Playwright with its own backend/SPA/database on
   private ports, pytest with a private database), with JUnit evidence. Pass = exit 0, ≥ 1 test from
   that file, no failure, error or skip. Manifest, harness, tool-config and existing-test edits, and
   agent configuration files the builder wrote, are refused before anything runs. A declared test that was not written, or a test file with no trusted runner, fails. A
   failure goes back to the builder with the controller's own output for at most `--repair-rounds`
   (default 1) more turns in the **same attempt** with the same model and effort; then the attempt
   blocks before cold review. The gate may not change the candidate (content-hash check). The
   builder's prompt now says the gate exists and how to run each kind of test itself.

5. **Attempt history survives replacement tickets** (toolkit 0.3.4): a ticket may declare
   `supersedes: [ids]`; it inherits the highest attempt count and closes those tickets (REJECTED,
   history kept). A ticket sharing at least half the paths of an unfinished ticket that has used
   attempts is refused unless it declares `supersedes` or a recorded `unrelated_to` reason; an
   exhausted history cannot be renamed. Conversely, host/account refusals (exit 75: dependency
   install, host checks, a model/effort the bridge refuses) block **without** charging an attempt;
   an agent cannot produce that exit code itself.

6. **Reproducible toolkit release**: the toolkit stays outside the repository, but its upgrade is
   reviewed here as a patch against the pinned 0.3.3 archive (SHA-256 `1247c45b…`).
   `ops/factory/toolkit_release.py build` reproduces 0.3.4 and checks the runtime pins and a manifest
   that must list exactly the files present; `verify` checks an installed copy.

7. **Independent architecture review.** The change was reviewed at Fable 5.2 / high effort before
   merge. Its findings (effort side channels via per-model caps, settings `env` blocks and thinking
   variables; the gate trusting the builder's tree; per-runner instead of per-file results; an
   evadable rename rule; attempts burnt by infrastructure; repair-round evidence not recorded) are
   fixed in this change, each with a regression test.

## Consequences

- A builder's claim that tests pass is replaced by controller-run evidence; U02-style defects stop
  in about a minute at the gate instead of after an hour of cold verification (measured: the real
  gate rejects the U02 attempt-2 candidate in ~30 s, Playwright 1 failure, vitest 5 passed).
- Cold verification is unchanged: every selected suite still runs twice in fresh checkouts, and
  both reviewers still review independently in fresh profiles. The gate adds time to every builder
  run that touches tests (one targeted Playwright run starts the full stack, ~15–40 s).
- A repair round costs one more builder turn at the builder's model and effort, but no attempt.
  `--repair-rounds 0` restores block-on-first-failure.
- Effective effort remains unverifiable from outside the CLI; the bridge controls and records every
  input it can. Organisation-level effort caps on the account are invisible locally. Codex runs
  record the requested pair but cannot be checked for substitution.
- Model availability is checked at configuration time (a few tokens per distinct pair) and on every
  run (served-model check). A model withdrawn from the account blocks tickets instead of degrading.
- The toolkit is now a local fork (0.3.4) of the upstream archive; upstream releases need rebasing
  this patch, reviewed like any other change.
- `routing_report.py` turns ledger + evidence into per-model/effort outcomes and cost; defaults
  change only on evidence from completed tickets (runbook "Evaluating the routing").

## Alternatives considered

- **Environment variables only, no toolkit change.** Rejected: reviewers run in a scrubbed
  environment, so an inherited effort variable never reaches them, and nothing would record or check
  the served model.
- **Fail the attempt on the first gate failure (no repair round).** Kept available
  (`--repair-rounds 0`), not the default: the builder never saw its own failure in either U02
  attempt, so one bounded feedback turn is the cheapest fix and costs no attempt budget.
- **A third, Fable-only reviewer lens for critical tickets.** Rejected for now: each lens runs every
  suite in its own cold checkout, so a third lens adds a full verification pass. Escalating the
  specification lens's model gives a second model family on critical work without that cost.
- **Trusting the builder transcript to show tests ran.** Rejected: a transcript is the builder's
  own account. The gate executes the tests itself; the transcript is kept for diagnosis only.
