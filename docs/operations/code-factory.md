# Agent ticket factory (Infra Code Factory) — runbook

Decision and rationale: [ADR-0029](../architecture/adr/0029-agent-ticket-factory.md).

The factory builds **two independent tickets in parallel** with local coding-agent CLIs, verifies
each candidate in fresh ("cold") checkouts against Vanshavali's real test suites, has fresh
reviewers attest to the exact candidate and evidence (standards and spec always, plus the specialist
lenses the diff selects), has an independent assessor rate its risk, and publishes **draft** PRs. It
never merges or deploys: CI and a person still decide. Everything here runs on *your* computer.

Toolkit version: **Infra Code Factory 0.5.0** plus its local-pilot hardening (Code-factory commit
`a780fce`), pinned by hash in `ops/factory/configure_factory.py`.

```
ticket JSON ─► factory run ─► dependency bootstrap ─► builder (worktree) ─► changed-test gate ─► one candidate commit
                                   │ scope + "don't weaken tests" guard
                                   ▼
     cold checkout per lens ── preflight + required suites ──► reviewers: standards, spec
                                                              + security / data / provenance /
                                                                frontend when the diff selects them
                                   │ all PASS
                                   ▼
                    independent risk assessor ─► low/medium ─► READY
                                                 high/critical ─► AWAITING_HUMAN ─► `approve` ─► READY
                                                                                    │
                    READY ─► publish (re-checks everything) ─► draft PR ─► CI + human merge
```

## What is in this repository

| Path | Purpose |
|---|---|
| `ops/factory/bootstrap_builder.py` | Controller-owned step every builder starts through: host checks, dependencies from the committed lockfiles, the agent, then the changed-test gate |
| `ops/factory/changed_test_gate.py` | Trusted gate: runs every new/changed/declared test in a fresh copy of the builder's changes before the work is accepted (ADR-0030) |
| `ops/factory/routing_report.py` | Per model/effort outcomes, gate results, cold failures and cost, from the ledger and evidence |
| `ops/factory/tests/` | Regression tests for the factory tooling (`make factory-test`; run in CI) |
| `ops/factory/run_suite.py` | Trusted wrapper: installs deps in the cold checkout, provisions a private DB/ports, runs one suite, writes JUnit |
| `ops/factory/pytest_kinds.py` | pytest plugin splitting the backend suite into unit / api / integration / migration |
| `ops/factory/configure_factory.py` | Generates the git-ignored `.infra-factory/config.json` for your machine; holds the pinned toolkit hashes, model routing and the review/risk policy (`REVIEW_POLICY`) |
| `ops/factory/tests/test_configure_factory.py` | Regression tests for the generated configuration (routing, policy, check argv, state-directory layout) |
| `ops/factory/examples/*.json` | Ticket templates (frontend-only and backend-only) |
| `e2e/playwright.visual.config.ts`, `e2e/visual/` | Visual-regression suite (required by the factory for frontend work) |

The toolkit itself is **not** in the repository. Keep it in a tools directory, e.g.
`~/tools/infra-code-factory` (a checkout of [Code-factory](https://github.com/ManishPandey21/Code-factory)
at the pinned commit). Its ledger, worktrees and logs live in `<git-common-dir>/infra-factory/`, which
on a factory clone (setup step 3) is outside any `.git` directory.

## Which suites a ticket runs

Chosen from the ticket's `paths` (ADR-0029 §5):

| Ticket touches | Suites (each run twice, once per review lens) |
|---|---|
| only `frontend/` (not the generated API client) | frontend unit, component, visual, e2e |
| only `backend/` | backend unit, api, integration, migration + shared contract + e2e |
| `frontend/openapi.json` or `frontend/src/api/`, both stacks, or anything else (`e2e/`, `docs/`, `renderer/`, ...) | everything |

Every run also executes the preflight: ruff, ruff format, mypy, eslint, tsc and the Vite build.
A suite passes only with ≥ 1 test, 0 failures and **0 skips**. The suites run once per selected
review lens (each lens gets its own cold checkout), so a backend ticket that touches `authz` runs
them three times (standards, spec, security).

## Reviews, risk and human approval (toolkit 0.5.0)

`REVIEW_POLICY` in `ops/factory/configure_factory.py` is the project's reviewed policy:

| Specialist lens | Selected when the diff touches | Checks |
|---|---|---|
| `security` | `backend/app/authz`, `api`, identity, consent, public, sharing, takedown, ownership, documents, archive, GEDCOM, property, the security-relevant `core` files, `deploy/`, `docs/security/` | CLAUDE.md rule 5: authz on every handler, IDOR/BOLA, cross-tree, living/child data, share links, uploads/downloads, exports; negative tests + threat/privacy model |
| `data` | `backend/alembic`, `backend/app/models`, `core/db.py`, the domain-model doc | Rules 3–4: canonical schema, migration with downgrade, single head, doc in sync |
| `provenance` | documents, evidence, extraction, smartadd, review, merge modules | Rule 7: OCR/AI/merge output never overwrites canonical data |
| `frontend` | `frontend/src`, `frontend/index.html` | Rule 9: accessibility, mobile, Indic scripts, en/hi parity, 403 states, ADR-0026 lists, kinship terms |

Globs are Python `fnmatch` (`*` crosses `/`) on every changed path, deleted ones included. Standards
and spec reviews remain mandatory for every ticket.

**Risk.** After the reviews pass, a separate `risk_assessor` (no builder transcript, no review
conclusions) rates the exact candidate. The controller raises its rating to the policy floor: **high**
for authz, identity, consent, public, sharing, property, `core/security.py`, `core/storage.py`,
migrations, `deploy/` and `.github/`; **medium** for the rest of `backend/` and `e2e/`; `role: critical`
tickets are always **critical**. High and critical candidates stop at **AWAITING_HUMAN**: they keep
their paths reserved and cannot publish until a person reviews the diff, every lens and the risk
rationale in `status`, then attests to that exact candidate:

```bash
python3 ~/tools/infra-code-factory/factory.py approve --repo . --ticket VSH-101 --head CANDIDATE_SHA --risk-digest DIGEST_FROM_STATUS --reviewer "Your name" --note "What you checked and why the risk is accepted"
```

The digest is `review_json.risk.digest` in `status`. An approval binds to that head, configuration
and risk digest only; a repaired candidate needs a new one. It is a local operator attestation, not
authentication. Never let an agent run `approve`.

## Builder dependencies (bootstrap)

Builders may run tests but may **never** install packages: their Claude permissions allow test,
lint and type-check commands only. A builder worktree is a fresh `git worktree` with no
`node_modules` or `.venv`, so the factory provisions it *before* the builder starts.
`configure_factory.py` makes every builder command (frontend, backend, critical; Claude or Codex)
start through `ops/factory/bootstrap_builder.py`, owned by the controller:

1. It refuses to run anywhere but the top level of a linked worktree inside
   `<git-common-dir>/infra-factory/worktrees`.
2. It checks that `backend/uv.lock`, `frontend/package-lock.json` and `e2e/package-lock.json` are
   byte-identical to the committed versions (by content hash, so index flags such as
   `--assume-unchanged` cannot hide a change), and that any install configuration present
   (`.npmrc`, `uv.toml`, `backend/.python-version`) is committed and unmodified too.
3. It runs `uv sync --frozen`, `npm ci` (frontend, e2e) and `npx playwright install chromium`, with
   the same download caches as the cold checks (`--cache-dir`). `npm ci` always replaces
   `node_modules`, so a stale or partial install from an earlier run is never trusted.
4. It checks that no changed or untracked file in the worktree was altered (by content, so a second
   edit to an already-modified file in a reused worktree is caught), writes `dependencies ready … starting builder` to the
   builder log, and then starts the unchanged agent command (with `--gate`, which the generated
   configuration always passes, as a child followed by the changed-test gate below). Only `PLAYWRIGHT_BROWSERS_PATH` is
   pointed at the cached browsers.

**Failures stop the ticket; they never widen permissions.** Any failure (missing or modified
lockfile or install configuration, a tool missing from `PATH`, an install error, a 20-minute step
timeout (the bootstrap kills its process group, so install scripts stop too), an altered worktree file, the wrong directory,
an agent command that cannot start) prints `[bootstrap] FAILED: …` in the ticket's `builder.log`,
exits non-zero before the agent starts, and the factory marks the ticket BLOCKED. Nothing falls
back to `npm install`, skips a component, or adds a permission. Fix the cause, then `retry`.
**Each failed bootstrap uses one of the ticket's three attempts** (the factory counts the attempt
before the builder command runs), so check the host before retrying: a preflight on a scratch
worktree is described below.

**Retry and worktrees.** `retry` only sets a BLOCKED ticket back to PENDING. The next `run` creates
a **new** worktree and branch from the base (`<ticket>-<timestamp>`) and starts its builder there;
the previous worktree is passed to the builder as a read-only reference and is never reused or
installed into. Because the bootstrap runs inside the builder command, it provisions whichever
worktree the builder is given, new or reused; dependencies installed in another worktree are never
relied on. Leftover worktrees can be removed with `git worktree remove` once you no longer need
them (their logs stay in the ledger).

**Boundaries.** The installs run with the factory process's own rights (the same OS account; see
the toolkit's `AUDIT.md`), from lockfiles committed on the base branch. A ticket cannot change them:
lockfiles, manifests and `ops/factory/` are refused in builder diffs. Cold checks still install
their own dependencies in fresh checkouts and never use the builder's. Reviewers get no bootstrap.
The bootstrap time counts towards the builder's `timeout_seconds`. With `--network-env`, the
builder already inherits the factory's live environment, which wins: if any proxy variable is set
live, **no** proxy setting is taken from the saved file (mixing would let npm or Playwright pick a
stale `npm_config_*` or lowercase value); CA settings from the file only fill in what is unset. The
cold checks, which run with a scrubbed environment, use the file as is.

**Preflight before a retry.** To prove the host can provision a builder without spending an
attempt, create a scratch worktree in the factory's worktrees directory and run the bootstrap with a
harmless command in place of the agent. Run both commands from the main checkout, with the
`--cache-dir` (and `--network-env`, if any) you gave `configure_factory.py`:

```bash
WT="$(git rev-parse --path-format=absolute --git-common-dir)/infra-factory/worktrees/PREFLIGHT"; git worktree add --detach "$WT" main
```

```bash
REPO="$PWD"; cd "$WT" && python3 -I "$REPO/ops/factory/bootstrap_builder.py" --cache-dir ~/.cache/vanshavali-factory -- sh -c "cd frontend && npx vitest run src/i18n"; cd "$REPO"
```

The log must end with `dependencies ready … starting builder` and a passing test run. Remove the
scratch worktree afterwards with `git worktree remove --force "$WT"`.

## Changed-test gate

A builder's statement that its tests pass is not evidence ([ADR-0030](../architecture/adr/0030-factory-changed-test-gate.md)).
Every builder command written by `configure_factory.py` passes `--gate` to the bootstrap, so after
the agent stops and **before the controller commits**:

1. Agent configuration (`.claude/`, `.mcp.json`, `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md`) must be
   exactly what is committed, ignored files included; this is also checked before every agent turn.
2. Changes the factory would reject anyway are refused before anything from them runs: manifests and
   lockfiles, `*.config.*`, `tsconfig*.json`, `.gitignore`, the test harness, and any edit to an
   existing test.
3. The bootstrap creates a **fresh worktree** at the base with exactly the builder's changed and new
   files, installs dependencies there itself, and runs each test file below **one file per run**,
   with runners that never install anything (`npx --no-install`, `uv run --frozen --no-sync`).
   Nothing the builder left in ignored files (`node_modules`, `.venv`, `.env`) affects the result.
   The copy is removed afterwards.

Test files run: every one the builder created or changed, and every one listed in the ticket's
`paths`:

| Test file | Command (in) |
|---|---|
| `frontend/**/*.test.ts(x)` | `npx vitest run <files>` (frontend/) |
| `e2e/tests/**/*.spec.ts` | `npx playwright test <files>` (e2e/; starts its own backend, SPA and database on private ports) |
| `e2e/visual/**/*.spec.ts` | the same with `--config=playwright.visual.config.ts` |
| `backend/tests/**/test_*.py` | `uv run pytest <files>` (backend/; private database, ephemeris, Tesseract) |

Each file passes with exit 0, at least one test **from that file** and no failure, error or skip. A
declared test file that was not written, a test file with no trusted runner (e.g. `renderer/`) or a
file name a runner could read as an option fails. A ticket with no new or declared tests passes the
gate with `no_tests: true` recorded (cold verification still runs every suite). On failure the
builder gets the controller's output (the end of the runner log) for `--repair-rounds` more turns
(default 1) within **the same builder command and attempt**, then the command fails with
`[bootstrap] FAILED: new or changed tests did not pass under the controller` and the ticket blocks.
A repair round is not started with less than 15 minutes left of the builder command's limit
(`timeout_seconds`, 5400 s for install, builder, gate and repair together). This is separate from
0.5.0's `factory.py repair` (below), which starts a new candidate and uses the attempt budget.

**Exit codes.** Work failures (the gate, a rejected change, a failing builder) exit 4 or the agent's
own code. Host or account refusals before or around the agent (dependency install, host checks,
the gate module not being the pinned one, a model or effort the bridge refuses) exit **75**, so
`builder.log` shows a host problem rather than the work. Toolkit 0.5.0 still **charges the attempt**
for either: fix the host before retrying. An agent's own exit 75 is never passed through. Evidence:
`changed-tests.json` plus `changed-tests-N-<runner>.log`/`.junit.xml` in the ticket's log
directory. The gate never edits the candidate (checked by content hash) and does not replace cold
verification, which still runs every selected suite in every review lens.

**Routing report.** After tickets complete, from the factory clone:

```bash
python3 ops/factory/routing_report.py --repo .
```

It lists, per builder model and effort, attempts, those that passed review (READY, AWAITING_HUMAN or
MERGED), blocks at the gate and in cold checks, repair rounds used, cost and tokens, then each
attempt with its standards and spec verdicts (`--json` for one record per attempt). Change a model
or effort default only when several tickets point the same way, in a reviewed PR that quotes it.

## One-time setup (factory host)

Host requirements: Git ≥ 2.29 (the toolkit checks), Python ≥ 3.10, [uv](https://docs.astral.sh/uv/), Node 22 + npm, Tesseract
with Hindi data (`tesseract-ocr tesseract-ocr-hin`), a **local** PostgreSQL 16 with the dev role
from the README (`vanshavali`/`vanshavali`, allowed to create databases), the `claude` CLI (and
`codex` for the default mixed providers), and `gh` for publishing. Never run the factory on a
machine that holds production credentials.

1. Get the toolkit outside the repository at the pinned commit and run its self-test:

   ```bash
   git clone https://github.com/ManishPandey21/Code-factory ~/tools/infra-code-factory
   ```

   ```bash
   git -C ~/tools/infra-code-factory checkout a780fce
   ```

   ```bash
   python3 -m unittest discover -s ~/tools/infra-code-factory/tests -v
   ```

2. Install the Superpowers plugin (provides the `test-driven-development` skill the builders
   follow) **in the Claude profile the factory runs under**, and note the path of its
   `test-driven-development/SKILL.md`. See the toolkit's `docs/SKILL_ROUTING.md`. Builders run as
   headless Claude, which refuses to read files outside its worktree by path; they load the skill
   through Claude's Skill tool instead, so the plugin must be installed and enabled, not just
   present on disk. A stand-alone copy of the file elsewhere is not readable by builders.

3. **Use a dedicated factory clone with a separate Git directory.** The toolkit puts builder
   worktrees in `<git-common-dir>/infra-factory/worktrees/`. In a normal clone that is inside `.git`,
   where Claude Code refuses to edit any file (every Claude builder stops with its edits refused as
   "sensitive file" changes and the ticket blocks with "Builder produced no changes"). Toolkit 0.5.0
   also refuses any symlink on the path of a cold checkout, so the old workaround (symlinking
   `.git/infra-factory/worktrees` elsewhere) now blocks every ticket. A clone whose Git directory is
   *not* named `.git` avoids both:

   ```bash
   git clone --separate-git-dir ~/vsh-factory-gitdir https://github.com/ManishPandey21/Vanshavali ~/vsh-factory
   ```

   Run every factory command from `~/vsh-factory`. Its state then lives in
   `~/vsh-factory-gitdir/infra-factory/`, with no `.git` component and no symlink.
   `configure_factory.py --apply` refuses a checkout whose state directory is inside `.git` or whose
   `worktrees` is a symlink.

   *Migrating an existing host* that used the symlink: with no ticket in flight, keep the old
   checkout (its ledger holds your history and logs) and start the new clone with a fresh ledger;
   re-`add` any PENDING tickets there. Do not copy `infra-factory/` across: its recorded worktree
   paths point at the old location.

4. In the factory clone, on a clean `main`, initialise the ledger:

   ```bash
   python3 ~/tools/infra-code-factory/factory.py init --repo . --apply
   ```

5. **Let builders run the tests.** Builders run as headless Claude in `acceptEdits` mode, where
   every shell command needs permission and an unanswered prompt is a refusal. Without the rules
   below a builder cannot run a single test, so it cannot see a test fail and then pass, and its
   mistakes only surface in cold verification (the first live ticket blocked this way). Add these
   rules to the Claude user settings of the account the factory runs under,
   `~/.claude/settings.json` (merge them into an existing `permissions.allow` list):

   ```json
   {
     "permissions": {
       "allow": [
         "Bash(npx vitest *)",
         "Bash(npm run lint)",
         "Bash(npm run typecheck)",
         "Bash(npm test *)",
         "Bash(npx playwright test *)",
         "Bash(npx tsc *)"
       ]
     }
   }
   ```

   They allow test, lint and type-check commands only; installs, Git and everything else still
   need a person. The rules apply to every Claude session of that account, not just builders.
   Claude Code will not edit its own settings from inside a session, so add them yourself.

   Put them in **user** settings, not in the repository's `.claude/settings.json`. Claude Code
   ignores permission rules in a project settings file until that folder has been trusted, and
   every builder runs in a brand-new worktree that never has been, so committed rules are
   silently skipped ("Ignoring … permissions.allow entries … this workspace has not been
   trusted"). On a cloud factory host, have the environment's setup script write the user
   settings file before Claude starts.

6. Generate the configuration (preview first, then `--apply`). The script accepts only the
   reviewed toolkit (Infra Code Factory **0.5.0** + hardening, commit `a780fce`), checked by SHA-256 of
   every module the controller loads, pinned in `ops/factory/configure_factory.py`; any other or
   modified copy is refused. To upgrade the toolkit, review its diff and update
   `TOOLKIT_VERSION`/`TOOLKIT_SHA256` in a normal PR.

   Every agent runs with the toolkit's **strict routing**: a pinned, full model id (aliases such as
   `opus` are refused), an explicit effort, no model fallback, and a check that the requested model
   actually served the run. No model id is assumed: pass the ones your accounts can use.

   ```bash
   python3 ops/factory/configure_factory.py --toolkit ~/tools/infra-code-factory --tdd-skill /path/to/test-driven-development/SKILL.md --claude-builder-model CLAUDE_MODEL_ID --claude-review-model CLAUDE_MODEL_ID --codex-model CODEX_MODEL_ID
   ```

   ```bash
   python3 ops/factory/configure_factory.py --toolkit ~/tools/infra-code-factory --tdd-skill /path/to/test-driven-development/SKILL.md --claude-builder-model CLAUDE_MODEL_ID --claude-review-model CLAUDE_MODEL_ID --codex-model CODEX_MODEL_ID --apply
   ```

   Default routing (`--providers mixed`): Codex builds backend and critical tickets, runs the
   standards review and the risk assessment; Claude builds frontend tickets and runs the spec and
   specialist reviews. `--providers claude` uses Claude for every role (no `--codex-model`). Builders
   are chosen by the ticket's `role`; the optional `complexity` field does not change the model.

   | Role | Effort (Claude / Codex) |
   |---|---|
   | `frontend`, `backend` builders | medium / medium |
   | `critical` builder | xhigh / high |
   | `reviewer_standards`, `reviewer_spec`, specialists, `risk_assessor` | high / high |
   | `reviewer_*_critical` (used for `role: critical`) | max / high |

   Other options: `--route ROLE=PROVIDER:MODEL:EFFORT` (override one role, e.g.
   `--route reviewer_security=claude:MODEL_ID:max`), `--skills-inventory FILE` (instead of
   `--tdd-skill`: a verified Matt/Superpowers inventory; builders also get the helper skills),
   `--ci-workflow-id ID` (allow `repair --source github` from that GitHub Actions workflow; find the
   id with `gh api repos/ManishPandey21/Vanshavali/actions/workflows`), `--egm` (require approved EGM
   design handoffs on every ticket), `--repair-rounds 0|1|2` (changed-test gate feedback turns,
   default 1), `--cache-dir`, `--pg-admin-url` (must be localhost). Behind a
   proxy or private CA add
   `--network-env ~/.config/vanshavali-factory/network.env --capture-network-env`: the factory
   strips the environment from test runs, so the proxy/CA variables of your shell are saved to
   that private (0600) file and only those allow-listed names are read back.

7. Record visual baselines **for your platform** once (Linux baselines are committed; macOS and
   Windows render fonts differently). Look at every image before committing them:

   ```bash
   cd e2e && npx playwright test --config=playwright.visual.config.ts --update-snapshots
   ```

8. Optional dry run of every suite on `main`, exactly as the factory would (slow; it proves the
   host is set up): add the two example tickets under new ids, run, then `reject` them.

## Daily use

Write tickets with the coordinator session (grill-me → to-spec → to-tickets in the toolkit's
terms). Each ticket is JSON like `ops/factory/examples/`; `paths` must list every file it may
create or change, **including its new tests**, and `spec` must cover `ui`, `api`, `data` and
`cross_cutting` (impact + acceptance, or a not-applicable reason). Keep ticket files outside the
checkout.

```bash
python3 ~/tools/infra-code-factory/factory.py add --repo . --ticket ~/vsh-tickets/VSH-101.json
```

```bash
python3 ~/tools/infra-code-factory/factory.py run --repo .
```

```bash
python3 ~/tools/infra-code-factory/factory.py run --repo . --execute --limit 2
```

```bash
python3 ~/tools/infra-code-factory/factory.py status --repo .
```

```bash
python3 ~/tools/infra-code-factory/factory.py publish --repo . --ticket VSH-101 --execute
```

`run` without `--execute` shows what would start and why everything else waits. Inspect a READY
ticket's diff, every review and the evidence (`status`) before publishing. A ticket in
AWAITING_HUMAN needs `approve` first (see "Reviews, risk and human approval"). After you merge a draft
PR **with a merge commit** (so the candidate stays an ancestor of `main`), pull `main`; dependants
then become eligible. Squash/rebase merges are not recognised; see the toolkit README.

Failures: `retry` (after diagnosing; three attempts max), `reject`, `recover`, `unlock` — see the
toolkit's `docs/HARDENING_SETUP.md`.

**Bounded repair.** Instead of a blind `retry`, a candidate whose review returned CHANGES_REQUIRED
(or, with `--ci-workflow-id`, whose allowlisted CI run failed on that exact commit) can be rebuilt
from those findings. Preview first; each `--execute` is one attempt from the same budget of three:

```bash
python3 ~/tools/infra-code-factory/factory.py repair --repo . --ticket VSH-101 --head CANDIDATE_SHA --source review
```

```bash
python3 ~/tools/infra-code-factory/factory.py repair --repo . --ticket VSH-101 --head CANDIDATE_SHA --source github --run-id RUN_ID --execute
```

A repaired candidate gets a new branch and a full re-verification; publish it as a new draft and
close the old one.

**Pausing and watching.** `hold` / `release` pause an inactive ticket durably (they take the
`--hold-version` shown by `status`). `add --idempotent` repeats an identical submission safely. To
watch progress live, `factory.py events --repo . --after 0 --follow`, or
`factory.py dashboard --repo . --port 8765` and open `http://127.0.0.1:8765` (loopback-only and
read-only). See the toolkit's `docs/TICKET_CONTROLS.md` and `docs/ASSURANCE_OPERATIONS.md`.

## Writing tickets that can pass

- **Independent means independent.** Two tickets run together only if their paths don't overlap,
  but the factory cannot see semantic coupling. Serialise (with `depends_on`) anything sharing a
  migration, an RLS/authz change, the generated API client, i18n keys or kinship packs.
- **Builders cannot** edit existing tests or snapshots, `package.json`/lockfiles/`pyproject.toml`,
  any `*.config.*`, `.gitignore`, `ops/factory/`, the test harnesses, `alembic.ini`, `CLAUDE.md`
  or `.github/`. A ticket that needs one of these (a new dependency, a changed baseline, an
  updated assertion) is done as an ordinary reviewed PR, then the dependent ticket runs.
- **Locales.** `en.json` and `hi.json` are kept key-identical by a test: a ticket adding UI text
  must list both files in `paths`.
- **API changes** must regenerate `frontend/openapi.json` and `frontend/src/api/schema.d.ts`
  (`npm run gen:api`) and list them in `paths`; the contract check fails otherwise. That makes the
  ticket full-stack.
- **Migrations** need a downgrade and are covered by the migration suite; one migration ticket at
  a time (Alembic heads must not fork).
- **List every test file in `paths`.** The changed-test gate runs each declared test file and fails
  the attempt if one was not written. Name tests where their runner expects them (gate table above).
- **Security-sensitive work** (CLAUDE.md rule 5): put the threat-model/privacy-model updates and
  the required negative tests into the acceptance criteria and `paths`; use `role: critical`.

## What the evidence does and does not mean

READY means: one candidate commit, inside its declared paths, passed every selected suite once per
review lens in fresh checkouts, every selected reviewer attested to that exact commit and evidence
digest, and the independent risk rating was below the human-review threshold or a person attested
to it with `approve`. It does
**not** mean the tests are sufficient, that the change is safe to merge without CI, or that a
same-user process could not have tampered with local state (see the toolkit's `docs/AUDIT.md`).
The draft PR body says "LOCAL verification"; CI on GitHub is still the gate.

## Suite details and troubleshooting

- Every cold suite fails at once with `ModuleNotFoundError: No module named 'path_safety'` (or another toolkit module): the configuration starts the toolkit's `test_report.py` with `python3 -I`, which hides the toolkit's own modules. `configure_factory.py` uses `-s -E` since U02-VITALS-EDIT-C (12 Nov 2026); re-run it with `--apply` to regenerate an older configuration.
- Each suite uses database `vsh_factory_<hash>_<kind>` on the local server and, for Playwright,
  ports in 20000–28999 derived from the run's namespace, so your dev stack (8000/3000) and the
  normal E2E ports (8100/3100) are untouched.
- Downloads (uv/npm caches, Playwright Chromium, the DE440s ephemeris, Python 3.11 if missing)
  are cached in `--cache-dir`. `.venv` and `node_modules` are always installed fresh.
- The real Remotion render test is deselected (CI's `renderer` job runs it); nothing else is.
- Run one suite by hand from a clean clone: `python3 -I ops/factory/run_suite.py backend-unit .factory-test-output/u.xml`
  (`--static backend|frontend` for the preflight).
- "Cold check modified the candidate checkout": a suite wrote an untracked, non-ignored file;
  fix the suite (via a normal PR), not the ticket.
- "Builder produced no changes", and the builder's result says its edits were refused as
  "sensitive file" permission prompts: the worktrees are still inside `.git`. Move to a factory
  clone with a separate Git directory (setup step 3), then `retry` the ticket.
- "Path must not contain symlinks or reparse points" at the first cold checkout: the host still uses
  the old `worktrees` symlink, which toolkit 0.5.0 refuses. Same fix (setup step 3).
- "Configured check input requires separate policy review": the ticket touches a file named in a
  check command (only `ops/factory/run_suite.py` should be). Changes to verification go through a
  normal reviewed PR.
- A strict-routing failure (`RoutingError`, "requested model … did not serve the run", or an effort
  cap in Claude settings): the model id is not available to that account or a `maxEffortLevel`
  setting is lower than the role's effort. Fix the account/settings or regenerate with `--route`. A builder that reports it could not read its skill file
  means the Superpowers plugin is not installed in the factory's Claude profile (setup step 2).
- A builder's summary says its test commands were refused and its tests were never run: the
  permission rules from setup step 5 are missing. Expect its new tests to fail in cold
  verification; add the rules before retrying.
- `builder.log` ends with `changed-test gate FAILED` / `new or changed tests did not pass under the
  controller`: the builder's own tests failed under the controller after the repair rounds. Read
  `changed-tests.json` and the `changed-tests-N-*.log` files in the ticket's log directory.
- `viewer-denied.spec.ts` (and any spec verifying an email late in a run) fails with `429
  rate_limited` from `POST /auth/verify-email`: the backend limits token use to 30/minute per IP
  (hard-coded in `identity/service.py`), and a full e2e run from 127.0.0.1 can exceed it. Measured
  on `main`: 15 passes then 5 fast failures in 20 repeats. Tracked separately; not quarantined.
- `builder.log` ends with `[bootstrap] FAILED: …` and the ticket is BLOCKED: dependency provisioning
  failed and the builder never started (see "Builder dependencies"). Fix the host (tool on `PATH`,
  network, cache disk space) or the lockfile on the base branch, then `retry`. Do **not** give
  builders install permissions instead.
- Downloads fail with `ECONNREFUSED` to a local proxy port in cold checks: the proxy settings saved
  in `--network-env` are stale (a local proxy restarted on another port). Re-run
  `configure_factory.py … --network-env FILE --capture-network-env --apply` from a shell that has
  the current settings.
- A builder reports it could not run tests because dependencies are missing: the configuration was
  generated before the bootstrap existed. Re-run `configure_factory.py … --apply` from an
  up-to-date `main`; every builder `argv` must start with `bootstrap_builder.py`.
