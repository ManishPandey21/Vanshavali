# Agent ticket factory (Infra Code Factory) — runbook

Decision and rationale: [ADR-0029](../architecture/adr/0029-agent-ticket-factory.md).

The factory builds **two independent tickets in parallel** with local coding-agent CLIs, verifies
each candidate in two fresh ("cold") checkouts against Vanshavali's real test suites, has two
fresh reviewers attest to the exact candidate and evidence, and publishes **draft** PRs. It never
merges or deploys: CI and a person still decide. Everything here runs on *your* computer.

```
ticket JSON ─► factory run ─► builder (worktree) ─► one candidate commit
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

4. Generate the configuration (preview first, then `--apply`). The script verifies the toolkit
   against its `SHA256SUMS` and refuses a modified copy.

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
