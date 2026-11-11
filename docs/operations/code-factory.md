# Agent ticket factory (Infra Code Factory) — runbook

Decision and rationale: [ADR-0029](../architecture/adr/0029-agent-ticket-factory.md).

The factory builds **two independent tickets in parallel** with local coding-agent CLIs, verifies
each candidate in two fresh ("cold") checkouts against Vanshavali's real test suites, has two
fresh reviewers attest to the exact candidate and evidence, and publishes **draft** PRs. It never
merges or deploys: CI and a person still decide. Everything here runs on *your* computer.

```
ticket JSON ─► factory run ─► dependency bootstrap ─► builder (worktree) ─► one candidate commit
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
| `ops/factory/bootstrap_builder.py` | Controller-owned step every builder starts through: installs dependencies from the committed lockfiles, then starts the agent |
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

## One-time setup (factory host)

Host requirements: Git, Python ≥ 3.10, [uv](https://docs.astral.sh/uv/), Node 22 + npm, Tesseract
with Hindi data (`tesseract-ocr tesseract-ocr-hin`), a **local** PostgreSQL 16 with the dev role
from the README (`vanshavali`/`vanshavali`, allowed to create databases), the `claude` CLI (and
`codex` for the default mixed providers), and `gh` for publishing. Never run the factory on a
machine that holds production credentials.

1. Extract the toolkit outside the repository and run its self-test:

   ```bash
   python3 -m unittest discover -s ~/tools/infra-code-factory/tests -v
   ```

2. Install the Superpowers plugin (provides the `test-driven-development` skill the builders
   follow) and note the path of its `test-driven-development/SKILL.md`. See the toolkit's
   `docs/SKILL_ROUTING.md`.

3. On a clean `main` checkout, initialise the ledger:

   ```bash
   python3 ~/tools/infra-code-factory/factory.py init --repo . --apply
   ```

4. Generate the configuration (preview first, then `--apply`). The script accepts only the
   reviewed toolkit release (Infra Code Factory **0.3.3**), checked by SHA-256 of its runtime files
   pinned in `ops/factory/configure_factory.py`; any other or modified copy is refused. To upgrade
   the toolkit, review its diff and update `TOOLKIT_VERSION`/`TOOLKIT_SHA256` in a normal PR.

   ```bash
   python3 ops/factory/configure_factory.py --toolkit ~/tools/infra-code-factory --tdd-skill /path/to/test-driven-development/SKILL.md
   ```

   ```bash
   python3 ops/factory/configure_factory.py --toolkit ~/tools/infra-code-factory --tdd-skill /path/to/test-driven-development/SKILL.md --apply
   ```

   Useful options: `--providers claude` (Claude for every role if you don't use Codex),
   `--claude-builder-model`, `--claude-review-model`, `--codex-model`, `--cache-dir`,
   `--pg-admin-url` (must be localhost). Behind a proxy or private CA add
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
