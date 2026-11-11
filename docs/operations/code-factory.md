# Agent ticket factory (Infra Code Factory) — runbook

Decision and rationale: [ADR-0029](../architecture/adr/0029-agent-ticket-factory.md).

The factory builds **two independent tickets in parallel** with local coding-agent CLIs, verifies
each candidate in two fresh ("cold") checkouts against Vanshavali's real test suites, has two
fresh reviewers attest to the exact candidate and evidence, and publishes **draft** PRs. It never
merges or deploys: CI and a person still decide. Everything here runs on *your* computer.

```
ticket JSON ─► factory run ─► dependency bootstrap ─► builder (pinned model/effort) ─► changed-test gate ─► one candidate commit
                                   │ scope + "don't weaken tests" guard
                                   ▼
          cold checkout A ── preflight + required suites ──► reviewer: standards ─┐
          cold checkout B ── preflight + required suites ──► reviewer: spec ──────┤ both PASS
                                                                                  ▼
                                    READY ─► publish (re-checks everything) ─► draft PR ─► CI + human merge
```

## What is in this repository

| Path | Purpose |
|---|---|
| `ops/factory/bootstrap_builder.py` | Controller-owned step every builder starts through: host checks, dependencies from the committed lockfiles, the agent, then the changed-test gate |
| `ops/factory/changed_test_gate.py` | Trusted gate: runs every new/changed/declared test in the builder worktree before the work is accepted (ADR-0030) |
| `ops/factory/toolkit/*.patch`, `ops/factory/toolkit_release.py` | The reviewed toolkit upgrade (0.3.3 archive → 0.3.4) and the script that rebuilds and verifies it |
| `ops/factory/routing_report.py` | Per model/effort outcomes, gate results, cold failures and cost, from the ledger and evidence |
| `ops/factory/tests/` | Regression tests for the factory tooling (`make factory-test`; run in CI) |
| `ops/factory/run_suite.py` | Trusted wrapper: installs deps in the cold checkout, provisions a private DB/ports, runs one suite, writes JUnit |
| `ops/factory/pytest_kinds.py` | pytest plugin splitting the backend suite into unit / api / integration / migration |
| `ops/factory/configure_factory.py` | Generates the git-ignored `.infra-factory/config.json` for your machine |
| `ops/factory/examples/*.json` | Ticket templates (frontend-only and backend-only) |
| `e2e/playwright.visual.config.ts`, `e2e/visual/` | Visual-regression suite (required by the factory for frontend work) |

The toolkit itself is **not** in the repository. Keep it in a tools directory, e.g.
`~/tools/infra-code-factory`. Its ledger, worktrees and logs live in `.git/infra-factory/`.

## Which suites a ticket runs

Chosen from the ticket's `paths` (ADR-0029 §5):

| Ticket touches | Suites (each run twice, once per review lens) |
|---|---|
| only `frontend/` (not the generated API client) | frontend unit, component, visual, e2e |
| only `backend/` | backend unit, api, integration, migration + shared contract + e2e |
| `frontend/openapi.json` or `frontend/src/api/`, both stacks, or anything else (`e2e/`, `docs/`, `renderer/`, ...) | everything |

Every run also executes the preflight: ruff, ruff format, mypy, eslint, tsc and the Vite build.
A suite passes only with ≥ 1 test, 0 failures and **0 skips**.

## Builder dependencies (bootstrap)

Builders may run tests but may **never** install packages: their Claude permissions allow test,
lint and type-check commands only. A builder worktree is a fresh `git worktree` with no
`node_modules` or `.venv`, so the factory provisions it *before* the builder starts.
`configure_factory.py` makes every builder command (frontend, backend, critical; Claude or Codex)
start through `ops/factory/bootstrap_builder.py`, owned by the controller:

1. It refuses to run anywhere but the top level of a linked worktree inside
   `.git/infra-factory/worktrees` (the symlink target counts).
2. It checks that `backend/uv.lock`, `frontend/package-lock.json` and `e2e/package-lock.json` are
   byte-identical to the committed versions (by content hash, so index flags such as
   `--assume-unchanged` cannot hide a change), and that any install configuration present
   (`.npmrc`, `uv.toml`, `backend/.python-version`) is committed and unmodified too.
3. It runs `uv sync --frozen`, `npm ci` (frontend, e2e) and `npx playwright install chromium`, with
   the same download caches as the cold checks (`--cache-dir`). `npm ci` always replaces
   `node_modules`, so a stale or partial install from an earlier run is never trusted.
4. It checks that no changed or untracked file in the worktree was altered (by content, so a second
   edit to an already-modified file in a reused worktree is caught), writes `dependencies ready … starting builder` to the
   builder log, and then `exec`s the unchanged agent command. Only `PLAYWRIGHT_BROWSERS_PATH` is
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
git worktree add --detach .git/infra-factory/worktrees/PREFLIGHT main
```

```bash
REPO="$PWD"; cd .git/infra-factory/worktrees/PREFLIGHT && python3 -I "$REPO/ops/factory/bootstrap_builder.py" --cache-dir ~/.cache/vanshavali-factory -- sh -c "cd frontend && npx vitest run src/i18n"; cd "$REPO"
```

The log must end with `dependencies ready … starting builder` and a passing test run. Remove the
scratch worktree afterwards with
`git worktree remove --force .git/infra-factory/worktrees/PREFLIGHT`.

## Model and effort routing

Every agent role runs a **pinned model id with an explicit effort** (ADR-0030), set in
`ROUTES` in `ops/factory/configure_factory.py`:

| Role | Model / effort | Used for |
|---|---|---|
| `builder_routine` | Sonnet 5.5 / medium | Tickets without `complexity`, or `complexity: routine` |
| `builder_complex` | Opus 5.5 / high | `complexity: complex` (cross-module, tricky state, migrations) |
| `builder_critical` | Opus 5.5 / high | `role: critical` (authz, privacy, integrity, uploads, exports) |
| `reviewer_standards`, `reviewer_spec` | Opus 5.5 / high | Both cold review lenses |
| `reviewer_standards_critical` | Opus 5.5 / high | Standards lens for `role: critical` |
| `reviewer_spec_critical` | Fable 5.2 / high | Exceptional-risk escalation: specification lens for `role: critical` |

Outside the factory (your own Claude sessions, not launched by it): coordinator (tickets,
allocation, final report) Opus 5.5 / medium; architecture supervisor (ADRs, factory audits)
Fable 5.2 / high; read-only status summaries and ticket triage Sonnet 5.5 / low. Do not use Fable
for polling or ordinary coding unless you mean to.

The ticket's `paths` still decide **which suites run**; `role`/`complexity` only decide **which
model builds and reviews**, so routing can never skip a test or a review. Override one role with
`--route`, e.g. `--route builder_routine=claude:claude-opus-5-5:high`; aliases (`opus`) and effort
names the CLI does not document are refused.

What the bridge enforces on every run (`--strict-routing`), and why: the Claude CLI accepts an
unknown effort silently, lets `CLAUDE_CODE_EFFORT_LEVEL` override `--effort`, clamps to a settings
`maxEffortLevel` without saying so, and can fall back to another model. The bridge validates the
effort, sets flag and variable to the same value, removes model-remapping variables, disables
fallback, refuses a run a settings cap would clamp, and refuses the result unless the requested
model served it. It cannot see the *effective* effort (the CLI never reports it) or an
account-level cap. Each run leaves `<result>.routing.json` beside its result (requested vs. served
model, effort controls, tokens, cost, denied tool names, outcome; never credentials), and builders
leave `builder-result.transcript.jsonl`.

**Evaluating the routing.** After tickets complete, run:

```bash
python3 ops/factory/routing_report.py --repo .
```

It lists, per model and effort, attempts, READY/MERGED, blocks at the gate and in cold checks,
repair rounds used, cost and tokens, then each attempt. Change a default only when several
tickets of the same complexity point the same way (routine tickets repeatedly blocking on
Sonnet/medium; complex ones passing first time on Sonnet), in a reviewed PR that quotes the report.

## Changed-test gate

A builder's statement that its tests pass is not evidence. With `--gate` (always written by
`configure_factory.py`), after the builder stops and **before the controller commits**:

1. Agent configuration (`.claude/`, `.mcp.json`, `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md`) must be
   exactly what is committed, ignored files included; this is also checked before every agent turn.
2. Changes the factory would reject anyway are refused before anything from them runs: manifests and
   lockfiles, `*.config.*`, `tsconfig*.json`, `.gitignore`, the test harness, and any edit to an
   existing test.
3. The controller creates a **fresh worktree** at the base with exactly the builder's changed and new
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
gate with `no_tests: true` recorded (cold verification still runs every suite). On failure
the builder gets the controller's output (the end of the runner log) for `--repair-rounds` more
turns (default 1) within **the same attempt**, then the attempt blocks with
`[bootstrap] FAILED: new or changed tests did not pass under the controller`. A repair round is not
started with less than 15 minutes left of the builder command's limit (`timeout_seconds`, 5400 s for
install, builder, gate and repair together).

**Which failures cost an attempt.** Work failures (the gate, a rejected change, a failing builder)
exit 4 or the agent's own code and are charged. Host or account refusals before or around the agent
(dependency install, host checks, a model or effort the bridge refuses) exit **75**: the ticket blocks
with `InfraRefusal (attempt not charged)`. Neither the bridge nor the bootstrap ever passes an agent's
own exit 75 through. Evidence:
`changed-tests.json` plus `changed-tests-N-<runner>.log`/`.junit.xml` in the ticket's log
directory. The gate never edits the candidate (checked by content hash) and does not replace cold
verification, which still runs every selected suite twice.

## One-time setup (factory host)

Host requirements: Git, Python ≥ 3.10, [uv](https://docs.astral.sh/uv/), Node 22 + npm, Tesseract
with Hindi data (`tesseract-ocr tesseract-ocr-hin`), a **local** PostgreSQL 16 with the dev role
from the README (`vanshavali`/`vanshavali`, allowed to create databases), the `claude` CLI (and
`codex` for the default mixed providers), and `gh` for publishing. Never run the factory on a
machine that holds production credentials.

1. Build the reviewed toolkit (0.3.4) outside the repository from the upstream 0.3.3 archive and
   the reviewed patch, then run its self-test (131 tests). `build` refuses any other archive, a
   patch that does not produce the pinned runtime files, and an existing output directory:

   ```bash
   python3 ops/factory/toolkit_release.py build --archive ~/Downloads/infra-code-factory-v0.3.3.zip --out ~/tools/infra-code-factory-0.3.4
   ```

   ```bash
   python3 -m unittest discover -s ~/tools/infra-code-factory-0.3.4/tests -v
   ```

   `python3 ops/factory/toolkit_release.py verify --toolkit DIR` checks an installed copy: its
   `SHA256SUMS` must list exactly the files present and every hash must match. (The 0.3.3 archive
   fails this on purpose: it ships the 0.3.1 manifest, whose four stale entries are exactly the
   files 0.3.2/0.3.3 changed.)

2. Install the Superpowers plugin (provides the `test-driven-development` skill the builders
   follow) and note the path of its `test-driven-development/SKILL.md`. See the toolkit's
   `docs/SKILL_ROUTING.md`.

3. On a clean `main` checkout, initialise the ledger:

   ```bash
   python3 ~/tools/infra-code-factory/factory.py init --repo . --apply
   ```

4. Generate the configuration (preview first, then `--apply`). The script accepts only the
   reviewed toolkit release (Infra Code Factory **0.3.4**), checked by SHA-256 of its runtime files
   pinned in `ops/factory/configure_factory.py`; any other or modified copy is refused. To upgrade
   the toolkit, review its diff and update `TOOLKIT_VERSION`/`TOOLKIT_SHA256` in a normal PR.
   `--apply` first **probes every distinct model/effort** in the routing table through the real
   bridge (a few tokens each; see "Model and effort routing") and writes nothing if one is
   unavailable or another model answers.

   ```bash
   python3 ops/factory/configure_factory.py --toolkit ~/tools/infra-code-factory-0.3.4 --tdd-skill /path/to/test-driven-development/SKILL.md --providers claude
   ```

   ```bash
   python3 ops/factory/configure_factory.py --toolkit ~/tools/infra-code-factory-0.3.4 --tdd-skill /path/to/test-driven-development/SKILL.md --providers claude --apply
   ```

   Useful options: `--providers claude` (Claude for every role if you don't use Codex),
   `--route ROLE=PROVIDER:MODEL:EFFORT` (override one role; repeatable), `--repair-rounds 0|1|2`
   (changed-test gate feedback turns, default 1), `--codex-model`, `--cache-dir`,
   `--pg-admin-url` (must be localhost), `--skip-model-probe` (offline only; runs still refuse a
   wrong model). Behind a proxy or private CA add
   `--network-env ~/.config/vanshavali-factory/network.env --capture-network-env`: the factory
   strips the environment from test runs, so the proxy/CA variables of your shell are saved to
   that private (0600) file and only those allow-listed names are read back.

5. Record visual baselines **for your platform** once (Linux baselines are committed; macOS and
   Windows render fonts differently). Look at every image before committing them:

   ```bash
   cd e2e && npx playwright test --config=playwright.visual.config.ts --update-snapshots
   ```

6. Optional dry run of every suite on `main`, exactly as the factory would (slow; it proves the
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
ticket's diff, both reviews and the evidence (`status`) before publishing. After you merge a draft
PR **with a merge commit** (so the candidate stays an ancestor of `main`), pull `main`; dependants
then become eligible. Squash/rebase merges are not recognised; see the toolkit README.

Failures: `retry` (after diagnosing; three attempts max), `reject`, `recover`, `unlock` — see the
toolkit's `docs/HARDENING_SETUP.md`.

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
- **Security-sensitive work** (CLAUDE.md rule 5): put the threat-model/privacy-model updates and
  the required negative tests into the acceptance criteria and `paths`; use `role: critical`.
- **Complexity.** Add `"complexity": "complex"` for cross-module work, tricky state or migrations
  (Opus/high builder); leave it out for routine tickets (Sonnet/medium).
- **List every test file in `paths`.** The changed-test gate runs each declared test file and fails
  the attempt if one was not written. Name tests where their runner expects them (table above).
- **Replacing a blocked ticket** (re-scoped, corrected): give it a new id **and**
  `"supersedes": ["OLD-ID"]`. It inherits the old ticket's attempts and closes it. A ticket sharing
  at least half of the paths of an unfinished ticket that has used attempts is refused without
  `supersedes`; adding or dropping a path does not make it new. A ticket that used all three
  attempts cannot be renamed into a new budget: the work needs re-scoping by a person. Work that
  really is different declares `"unrelated_to": {"OLD-ID": "<reason>"}`, which the ledger records.

## What the evidence does and does not mean

READY means: one candidate commit, inside its declared paths, passed every selected suite twice
in fresh checkouts, and both reviewers attested to that exact commit and evidence digest. It does
**not** mean the tests are sufficient, that the change is safe to merge without CI, or that a
same-user process could not have tampered with local state (see the toolkit's `docs/AUDIT.md`).
The draft PR body says "LOCAL verification"; CI on GitHub is still the gate.

## Suite details and troubleshooting

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
- `builder.log` ends with `changed-test gate FAILED` / `new or changed tests did not pass under the
  controller`: the builder's own tests failed under the controller after the repair rounds. Read
  `changed-tests.json` and the `changed-tests-N-*.log` files in the ticket's log directory.
- `agent_bridge: … did not serve this run` / `maxEffortLevel … would silently clamp` /
  `not a full Claude model id`: strict routing refused the run (see "Model and effort routing").
  Check account access and settings files; never work around it by removing `--strict-routing`.
- `model probe failed for …` from `configure_factory.py --apply`: that model/effort is not available
  to this account. Choose another with `--route`, or fix access; nothing was written.
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
