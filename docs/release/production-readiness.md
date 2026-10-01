# Production readiness report

**Date:** 1 October 2026 · **Code:** branch `claude/pensive-tesla-yoojvh`, based on `main` at
`708171e` (PRs #6–#12 included). **Scope:** post-Phase-8 validation (environment, DAST,
performance, accessibility, full regression). All measurements were taken in the Claude Code
Cloud sandbox (4 vCPU shared VM, PostgreSQL 16.13) unless stated otherwise.

## Verdict
The code is **ready for a production pilot once the deployment items below are done**. It is
**not yet cleared for public launch**.

- **Validated:** every automated gate passes, and DAST executed with **0 FAIL / 0 WARN**.
- **Fixed in this pass:** six real defects found by this validation (two security, one data-input,
  one resilience, one OCR, one third-party privacy).
- **Performance:** meets the PRS §49 latency target for normal use and for sustained load up to
  50 req/s on this sandbox. Production capacity is still uncertified.
- **Blockers left:** operational and human. Production configuration (proxy addresses, SMTP,
  secrets, hosting), a performance certification on staging hardware, a backup drill on production
  infrastructure, a manual screen-reader pass, and legal plus native-Hindi review of the consent
  wording.

"Deployment blocker" below means it **blocks production go-live**.

## Readiness matrix

| Component | Status | Evidence | Measured result | Unresolved issue | Human action required | Deployment blocker |
|---|---|---|---|---|---|---|
| Backend API (all modules) | ✅ Pass | `uv run pytest` (as the RLS app role) | **312 passed**, 0 failed | — | — | No |
| Database migrations | ✅ Pass | clean DB: upgrade → `alembic check` → downgrade base → upgrade; `test_migrations.py` | 10 revisions, one head, no model drift, 0 tables left after downgrade | — | Run `alembic upgrade head` as the owner, then `app.cli.ensure_app_role` (deployment.md) | No |
| Tree isolation (authz + Postgres RLS) | ✅ Pass | `test_rls.py`, `test_route_isolation.py`; `/health/ready` reports `rls: enforced` | RLS overhead not measurable (−4.7 to +2.0 ms per endpoint, noise) | — | Connect the API and worker as the non-owner role (never the owner) | No |
| Frontend SPA | ✅ Pass | lint, typecheck, Vitest, production build | **122/122** Vitest; build OK | One onboarding test failed once at load average ~40 and passed 8 times since; not reproducible (see Observations) | — | No |
| End-to-end (Playwright) | ✅ Pass | `npx playwright test` (12 specs) | **26/26** passed, backend as the RLS role | — | — | No |
| Static security | ✅ Pass | ruff `S` (CI SAST), mypy, pip-audit, npm audit (frontend, e2e), gitleaks over the full history | 0 findings; 0 known vulnerabilities; gitleaks 3 hits, all test placeholders | — | — | No |
| **DAST** | ✅ Pass (sandbox) | ZAP baseline + **ID-aware** active API scan with the same image, rules and steps as `dast.yml`; reports in `evidence/dast-2026-10-01/` | Baseline **0 FAIL / 0 WARN / 60 PASS**; API **0 FAIL / 0 WARN / 113 PASS**, **0 server errors** | The first scheduled run on GitHub has not happened | Dispatch `DAST` once on GitHub and review the artifacts | No |
| Client IP and rate limiting behind proxies | ✅ Fixed | `test_proxy_headers.py`; DAST spoofing probe; manual reproduction | Before: spoofed `X-Forwarded-For` bypassed the login throttle (35/35 accepted). After: 5 × 429 even with rotating spoofed headers | Production proxy addresses unknown | Set `FORWARDED_ALLOW_IPS` to the exact nginx/LB addresses (deployment.md). With the loopback default, all users share one rate-limit bucket | **Yes** (configuration) |
| HTTP security headers, CSP, third parties | ✅ Fixed | DAST; Chromium check over 24 page loads | CSP is `'self'`-only (no `'unsafe-inline'`); 0 CSP violations; 0 third-party requests; nginx version hidden | — | — | No |
| Input robustness | ✅ Fixed | `test_input_robustness.py`; ID-aware DAST | NUL byte in input: unhandled 500 before, structured 422 now | — | — | No |
| **Performance, normal use** (PRS §49) | ✅ Meets (sandbox) | `loadtest sequential`, 10,000 people, 9 operations incl. writes | p95 **≤ 101 ms** for every operation (5× margin) | — | — | No |
| **Performance, sustained load** | ⚠️ Sandbox only | open-loop sweep, 3 runs that must agree (`ops/loadtest/certify.sh`) | 10–50 req/s: worst p95 **125–353 ms**, 0% errors, 3/3 runs | **Production capacity not certified**: API, DB and generator shared 4 vCPUs | Run the staging-host runbook (performance.md); size the fleet so peak ≤ 70% of certified capacity | **Yes** |
| Overload behaviour | ✅ Fixed | `test_overload.py`; sweeps at 60–80 req/s | Before: collapse (10 / 0 successful req/s at 70 / 80 offered; unhandled 500s and 60 s client timeouts). After: 63 / 62 successful req/s, p95 2.5 s, fast 503 + `Retry-After` | — | Alert on sustained `server_busy` 503s (add capacity) | No |
| Documents and OCR | ✅ Fixed | `test_extraction.py` incl. the concurrency regression | 4 concurrent OCR jobs: > 300 s each (timed out) before, 0.3 s each after | Handwriting and other Indic OCR languages deferred | — | No |
| Accessibility, automated | ✅ Pass | `a11y.spec.ts` (axe WCAG 2.0–2.2 A/AA + keyboard/semantics) | 0 serious/critical violations; **15 more pages** now scanned (en/hi); mobile "More" now announces the current section | — | — | No |
| Accessibility, assistive technology | ⏳ Outstanding | `docs/accessibility/manual-test-checklist.md` | not run (needs people and devices) | NVDA, JAWS, VoiceOver and TalkBack pass not done; chart node names cannot switch voice language | Run the checklist; record results here | **Yes** |
| Hindi language quality and consent wording | ⏳ Outstanding | checklist §3 (prioritised screens) | 1,809 Hindi strings exist (only "OCR" equals the English) | Consent and attestation text not reviewed by a native speaker or a lawyer (open question Q13) | Native-Hindi review; legal review of `consent/statements.py` and email templates | **Yes** |
| Email delivery | ⏳ Configure | `test_email_auth.py`; production refuses non-SMTP mailers | — | No production SMTP provider configured | Configure SMTP with STARTTLS, plus SPF/DKIM/DMARC for the sender domain. Registration depends on it | **Yes** |
| Secrets and keys | ⏳ Configure | `config.validate_production` refuses dev keys | — | — | Provision `VSH_STANDARD_DATA_KEY`, `VSH_VAULT_DATA_KEY`, `VSH_SIGNING_KEY`, DB passwords and `VSH_METRICS_TOKEN` from a secret manager | **Yes** |
| Backup and restore | ⚠️ Local only | `ops/backup/drill.sh` (Phase 8) | restore + verify 5.9–6.7 s at 10k people (local) | `drill.yml` not run on GitHub; PITR and S3 versioning not drilled | Enable managed PITR; run the drill against production-like infrastructure; record RPO/RTO | **Yes** |
| Observability | ✅ Implemented | `test_observability.py` | JSON logs, request IDs, readiness with RLS check, metrics | Alert rules and tracing deferred | Wire alerts: 5xx / `server_busy` rate, p95 per route, readiness, job failures, scanner down | No (do in week 1) |
| Container images | ⚠️ Partly verified | frontend image built and served in DAST; backend image: CI `docker` job | Frontend: built (production nginx, headers verified) | Backend image could not be built in the sandbox (GHCR and AWS ECR CDN blocked by egress policy; Docker Hub rate-limited) | Confirm CI `docker` job is green on this PR | No (if CI green) |
| Hosting | ⏳ Decide | implementation-plan §12 (ASSUMPTION) | — | Hosting provider and topology not decided | Choose hosting; deploy per `docs/operations/deployment.md` | **Yes** |
| Penetration test | ⏳ Deferred | — | — | No independent test | Commission an external penetration test (authz/BOLA, uploads, claim links) | **Yes** before public launch; No for a closed pilot |
| Environment cleanup | ✅ Done | `pg_database` / `pg_roles` listings | `vsh_frontend_dev` dropped (0 connections, no references, no dedicated role); every DB and role created here removed | — | — | No |

## Defects found and fixed in this pass
Each fix has a regression check: a test for #1–#4, and DAST FAIL rules plus a browser CSP check for
#5–#6. The tests for #2 and #4 were confirmed to fail without the fix. #1 was reproduced against the
production image before the fix and verified there after it.

| # | Defect | Found by | Severity | Fix (commit) |
|---|---|---|---|---|
| 1 | `X-Forwarded-For` trusted from any peer: a client chooses its own IP, bypasses per-IP login, registration and reset throttles, and falsifies audit and session IPs | DAST evidence ("Private IP"), then reproduced | **Medium** (security) | Trust only the configured proxies; DAST probe (`a2d70a9`, threat T30) |
| 2 | NUL byte in a query or JSON body → unhandled 500 outside the structured error format | ID-aware DAST | Low (robustness) | `DataError` → 422 `invalid_input` (`744e5c6`) |
| 3 | Overload collapse: pool waits of 30 s, unhandled 500s; at 70 / 80 req/s offered only 10 / 0 requests per second succeeded | Open-loop sweep | **High** (availability) | Admission control, 5 s pool wait, retryable 503 (`929c886`) |
| 4 | Concurrent OCR jobs time out (OpenMP thread thrash) | Regression under load | Medium (functional) | `OMP_THREAD_LIMIT=1` per tesseract (`8777509`) |
| 5 | Google Fonts on every page: no SRI possible, visitor IPs sent to a third party | DAST (SRI) | Low (privacy/supply chain) | Self-hosted fonts; CSP `'self'`-only (`d5649a8`) |
| 6 | nginx version disclosed; CSP allowed `'unsafe-inline'` styles | DAST | Low (hardening) | `server_tokens off`; strict CSP (`d5649a8`) |

**Tooling defects** were also fixed, so the measurements themselves can be trusted:
- the load-test seed couldn't write after ADR-0011;
- the sweep re-logged-in on every rate step, so Argon2 bursts landed in the measured window;
- keep-alive pinned connections to workers, so identical runs disagreed by 3×;
- `certify.sh` aborted at the first failing step;
- the DAST workflow didn't run the API with the production proxy flags, and gave the active scan
  placeholder IDs (99% of its requests stopped at validation).

## Regression results (final code)

| Gate | Command | Result |
|---|---|---|
| Backend tests | `uv run pytest` (RLS role) | 312 passed |
| Backend lint/format/types | `ruff check`, `ruff format --check`, `mypy app` | clean (one format fix committed: `13fa05d`) |
| SAST | `uvx ruff check --select S app` | clean |
| Python dependencies | `pip-audit -r <hashed export> --disable-pip` | no known vulnerabilities |
| Migrations | clean DB upgrade / check / downgrade / upgrade | pass |
| Frontend | `npm run lint && npm run typecheck && npm test && npm run build` | pass; 122 tests |
| npm dependencies | `npm audit` (frontend prod and all; e2e) | 0 vulnerabilities |
| End-to-end | `npx playwright test` | 26/26 |
| Secrets | gitleaks over the full history | 3 false positives (test placeholders) |
| DAST | ZAP baseline + ID-aware API scan | 0 FAIL / 0 WARN |
| Docker | frontend image build; backend image | frontend ✅; backend via CI only (sandbox egress) |

## Observations (not blockers)
- `onboarding.test.tsx` ("never pre-ticks the consent box…") failed once during a full Vitest
  run while the box had load average ~40 (ZAP + pytest running). The error text was not captured.
  It then passed in 2 full runs, 1 isolated run and 6 parallel stress runs. If it recurs in CI,
  capture the message before changing it.
- `/change-password` (forced password change) is not in the accessibility scan: it needs an
  account flagged `must_change_password`. Add a seeded account to the spec if that flow ships.
- People list: a sequential scan plus top-N sort that grows linearly with tree size (19 ms at
  33,765 people). The index is recorded in performance.md as a trigger for trees of about 100k
  people.

## How to reproduce
- **DAST:** `.github/workflows/dast.yml` (`workflow_dispatch`). Locally, follow the same steps
  with `zaproxy/zap-stable` and `.zap/rules.tsv`, and the ID file generated by the workflow's
  "Real IDs" step.
- **Performance:** `ops/loadtest/certify.sh`. For the two-host staging run, see
  `docs/operations/performance.md`.
- **Accessibility:** `make a11y`. For the manual pass, see `docs/accessibility/manual-test-checklist.md`.
