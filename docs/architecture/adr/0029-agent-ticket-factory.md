# ADR-0029: Agent ticket factory (Infra Code Factory) for locally verified draft PRs

- Status: **Proposed** · Date: 2026-11-11
- Relates to: CLAUDE.md working rules 1, 5, 8 (explore first; security-sensitive changes; testing),
  the CI workflow (`.github/workflows/ci.yml`), ADR-0022 (ephemeris), ADR-0017 (Remotion renders).
- Tooling: [Infra Code Factory 0.3.3](../../operations/code-factory.md) — a standalone, stdlib-only
  Python toolkit kept **outside** this repository.

## Context

Most changes to Vanshavali are written with coding agents (Claude Code, Codex). Today one session
writes, tests and opens a PR for one change at a time, and "the tests passed" is whatever that
session reports. The owner wants to run **two independent tickets in parallel**, each built by a
fresh agent in its own Git worktree, and to receive **draft PRs only after independent
verification** — with no automatic merge or deploy.

The Infra Code Factory toolkit implements exactly that loop: a deterministic local controller with
a SQLite ledger allocates at most two tickets, gives each builder a worktree, refuses out-of-scope
or verification-weakening edits, commits one candidate, then runs every required test category in
two **cold** checkouts (fresh Git repository, scrubbed environment) and asks two fresh reviewers
(a standards lens and a specification lens) to attest to the exact candidate and the hashed test
evidence. Only two PASS verdicts make a ticket READY; `publish` re-validates and opens a draft PR.

The toolkit is fail-closed and opinionated about evidence. Its hard-coded minimum test matrix is:

| Layer | Required kinds (toolkit minimum) |
|---|---|
| frontend | unit, component, **visual**, e2e |
| backend | unit, api, integration |
| shared | contract |

Each kind must produce native JUnit XML with ≥ 1 test, zero failures and **zero skips**; an exit
code alone never counts. Vanshavali had no visual-regression suite, its backend suite is one
pytest run, and several backend tests skip when a host dependency (Tesseract, the DE440s
ephemeris, a Remotion bundle) is missing.

## Decision

Adopt the factory as an **optional, local** delivery path. CI, branch protection and human review
remain the merge gate; nothing about `main` changes.

1. **Toolkit outside the repo, integration inside it.** The toolkit is extracted to a tools
   directory; the config generator accepts only the reviewed release, by SHA-256 of its runtime
   files pinned in `ops/factory/configure_factory.py` (the archive's own `SHA256SUMS` sits next to
   the code it describes, and 0.3.3 shipped a stale one). The repository carries only the integration in
   `ops/factory/`: the suite wrapper, a pytest classification plugin and a config generator. The
   generated `.infra-factory/config.json` holds machine-specific absolute paths and is git-ignored.
2. **Map real suites onto the toolkit's kinds** (`ops/factory/run_suite.py`), each runnable in a
   cold checkout (fresh `uv sync --frozen` / `npm ci`; only download caches are shared):

   | Check | Kind | What runs |
   |---|---|---|
   | backend-unit / -api / -integration / -migration | unit / api / integration / migration | `pytest`, partitioned by `ops/factory/pytest_kinds.py` (see below) |
   | frontend-unit | unit | vitest `*.test.ts` |
   | frontend-component | component | vitest `*.test.tsx` |
   | frontend-visual | visual | Playwright screenshot comparison, `e2e/visual` (new) |
   | frontend-e2e | e2e | the whole Playwright suite incl. axe accessibility checks |
   | shared-contract | contract | backend OpenAPI == `frontend/openapi.json`; `schema.d.ts` == generated |
   | preflight (exit code) | — | ruff, ruff format, mypy; eslint, tsc, vite build |

3. **Backend partition by what a test touches**, not by file lists, so new tests are classified
   automatically: a test that drives Alembic is *migration*; one that requests the `app` fixture
   (every HTTP client fixture depends on it) is *api*; one that otherwise touches the database is
   *integration*; the rest is *unit*. The four partitions are disjoint and cover the whole suite.
   Other kinds are deselected, never skipped.
4. **No skips.** Suites run with `VSH_REQUIRE_EPHEMERIS=1` and a checksum-verified cached
   ephemeris; Tesseract must be installed on the factory host. The single real-Remotion render test
   is **deselected** (it needs the renderer bundle and ffmpeg) and stays covered by CI's `renderer`
   job.
5. **Stricter than the toolkit minimum** for this project: any backend change also requires the
   migration suite, the API-contract check and the browser E2E suite ("a passing API test does not
   prove the browser workflow works"). `frontend/openapi.json` and `frontend/src/api` are the
   *shared* layer, so touching the generated contract runs everything. Paths outside `frontend/`
   and `backend/` (e2e, renderer, docs, deploy, ops) conservatively select the full stack.
6. **A visual-regression suite** (`e2e/playwright.visual.config.ts`, `e2e/visual/`): the landing
   page in English and Hindi and the sign-in, sign-up and password-reset forms, on desktop and a
   phone viewport, with reduced motion and **zero differing pixels** allowed. Baselines are per
   platform; a new factory host records its own once, by a person.
7. **Builders cannot change verification.** Beyond the toolkit's own refusals (edits to existing
   tests/snapshots, manifests, lockfiles, `*.config.*`, `.gitignore`), `protected_paths` covers
   `ops/factory/`, the pytest/Playwright harnesses (`conftest.py`, `helpers.py/ts`,
   `e2e/scripts`, `frontend/src/test`), `alembic.ini` and this ADR. New tests are allowed.
8. **Isolation for test resources.** Each suite gets its own database
   (`vsh_factory_<hash(namespace)>_<kind>`) and E2E ports derived from `FACTORY_NAMESPACE`; the
   generator refuses a non-local PostgreSQL admin URL. No `VSH_*` variable from the host reaches a
   check.
9. **Providers.** Default mapping follows the toolkit (Codex for backend builds and the standards
   review, Claude for frontend builds and the specification review, so the two lenses do not share
   one model's blind spots); `--providers claude` uses Claude for every role.

10. **Two small application changes the pilot showed were needed**, both inert outside the
    factory/E2E harness:
    - The toolkit keeps cold checkouts under `.git/infra-factory/`, which Vite's default
      `server.fs.deny` (`**/.git/**`) refuses, so Vitest and the E2E dev server could load no
      source. `frontend/vite.config.ts` drops only that entry when `VSH_FACTORY_COLD=1`, which only
      `run_suite.py` sets; the normal dev server keeps Vite's defaults.
    - The per-IP registration limit (20/minute) was hard-coded. On a fast host the E2E suite
      registers more accounts than that from 127.0.0.1 and fails with 429 (CI's slower runners pass).
      It is now `VSH_REGISTER_RATE_LIMIT_PER_MINUTE` (default unchanged, 20), raised only in
      `e2e/playwright.config.ts` next to the existing login-limit override; threat model T19 and
      `test_auth.py::test_registration_rate_limited_per_ip` cover it.

## Consequences

- Two tickets can be built concurrently and arrive as draft PRs with hashed, re-checkable evidence.
  READY is a *local* result: CI must still pass and a person still merges.
- Verification is slow by design: every candidate runs the selected suites twice (one per review
  lens) in fresh checkouts, serialised on the host. A backend ticket runs the whole backend suite,
  the contract check and the full E2E suite twice.
- Tickets that change an existing test, a manifest/lockfile (adding a dependency), a runner config,
  the generated client in a way the contract rejects, or a visual baseline are **refused** and need
  a separately reviewed change. Shared migrations, auth/RLS changes and generated contracts should
  be serialised, not split into "independent" tickets (the toolkit cannot see semantic coupling).
- The toolkit's limits apply unchanged (see its `AUDIT.md`): same-OS-account processes are not
  sandboxed, local evidence is unsigned, there is no automatic merge or rollback. Production
  secrets must never be present on a factory host.
- Security-sensitive tickets (CLAUDE.md rule 5) still need their threat-model/privacy-model updates
  and negative tests written into the ticket's acceptance criteria; the factory only verifies what
  the tests check.

## Alternatives considered

- **Vendor the toolkit into the repository.** Rejected: it would sit inside the candidate's
  write scope (the toolkit itself warns against this) and its state already lives in `.git/`.
- **Commit `.infra-factory/config.json`.** Rejected: it contains absolute host paths; the generator
  is the reviewed source of truth and is reproducible on any host.
- **Mark the visual kind not-applicable.** Not possible (the toolkit's minimum is hard-coded and it
  forbids no-op suites) and undesirable: Devanagari rendering and mobile layout are exactly what
  unit tests miss.
- **Classify backend tests by a hand-maintained file list.** Rejected: new test files would be
  silently unclassified; the fixture/source-based rule covers every collected test.
