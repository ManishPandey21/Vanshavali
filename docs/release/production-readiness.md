# Production readiness report

Two validations are recorded here, newest first:
1. **Pilot deployment and operational validation:** 2 Oct 2026, this section.
2. **Post-Phase-8 production-readiness validation:** 1 Oct 2026, kept below unchanged for the
   record.

# Pilot deployment and operational validation (2 Oct 2026)

**Code:**
- branch `claude/pensive-tesla-yoojvh`, based on `main` at `855cc29` (PR #13 merged);
- commits `1d84151`…`6187717`.

**Scope (milestone "Pilot Deployment & Operational Validation"):**
- the deployment architecture and its infrastructure as code;
- operations: email, secrets, backups, monitoring, release, incidents;
- validation of all of the above by running it.

**Where measured:** in the Claude Code Cloud sandbox (4 vCPU shared VM). No cloud account, VM, DNS
name or managed service exists yet. Everything "executed" below ran there, against stand-ins for
the managed services.

## Verdict: READY FOR CONTROLLED PILOT, conditional on the go-live checklist's Blocking section
- **Repository side: no blocker remains.**
  - The architecture is decided (ADR-0014).
  - Its stack, scripts, CI deploy gate, monitoring, runbooks and smoke test exist.
  - All of it was **executed end to end** on the real compose file and Caddyfile: deploy,
    email round trip, smoke test, backup, total loss, restore, verified service, second deploy,
    performance through the edge.
- **Defects:** this validation found 10, all fixed with regression tests or measured checks.
  Three would have hurt a pilot directly:
  - writes committed after the response;
  - the second deploy failing on managed PostgreSQL;
  - 250 MB GEDCOM imports refused at the proxy.
- **Not yet true:** the pilot environment does not exist. Every item still open in the
  **Blocking** section of `docs/release/pilot-go-live-checklist.md` is a **human action or an
  external dependency**:
  - provider account;
  - VM, DB and buckets;
  - DNS and TLS;
  - SMTP domain records;
  - secret escrow;
  - a restore drill and a performance certification on real infrastructure;
  - the minimum screen-reader pass;
  - native-Hindi review of the consent, privacy, registration and email texts.

  **Invite the first family only when that section is fully ticked.**
- **Not ready for public launch.** These remain open:
  - independent penetration test;
  - legal review (DPDP, open question Q13);
  - full assistive-technology and Hindi reviews;
  - production capacity certification;
  - data-key rotation tooling.

## Readiness matrix (pilot)
"Deployment blocker" = blocks the **controlled pilot**. Public-launch-only items say so.

| Component | Status | Evidence | Measured result | Unresolved issue | Human action required | Deployment blocker |
|---|---|---|---|---|---|---|
| Hosting decision | ✅ Decided (ADR-0014) | `docs/architecture/adr/0014-pilot-hosting.md` | — | Provider account not chosen (reference: AWS ap-south-1) | Confirm the provider and account; billing alerts | **Yes** |
| Infrastructure as code | ✅ Executed (sandbox) | `deploy/pilot/` (compose, Caddyfile, scripts, monitoring, drill); CI `deploy-config` job | 3 deploys and 1 restore of the real compose file in the drill | `bootstrap-host.sh` not run on a VM (shellcheck-clean only) | Run bootstrap on the staging and pilot VMs | **Yes** (provisioning) |
| Reverse proxy / TLS | ✅ Executed (local CA) | `evidence/pilot-2026-10-02/edge-test.md` | 308 to https; TLS 1.3 + HTTP/2; HSTS and CSP present; Server header removed; uploads 50 MB → 201, 60 MB → 413; imports 250 MB → 201, 270 MB → 413; unknown host refused | Real ACME certificate not yet issued | DNS A record; ports 80/443 open | **Yes** |
| Trusted proxies (T30) | ✅ Implemented + enforced | `test_proxy_headers.py`, `test_pilot_ops.py`; edge test | Spoofed `X-Forwarded-For` dropped at the edge; production refuses `*` or `/0` at start-up | Real client IPs depend on Docker's userland proxy being off (bootstrap sets it) | Check the session list shows your public IP on the pilot | **Yes** (check on the VM) |
| Database production setup | ✅ Executed (stand-in) | drill; `test_app_role.py`; migration CI step | Migrations as a **non-superuser owner**; app role created, then verified on every deploy | **Defect fixed:** every deploy after the first failed on managed PostgreSQL. PITR not exercised | Managed PG 16 with PITR, TLS, owner role; `max_connections` sizing | **Yes** (provisioning) |
| Object storage | ✅ Executed (moto stand-in) | drill; pilot plan §12 | Private bucket via app-encrypted objects; mirror and restore of every object; checksums verified after restore | Real bucket policy, Block Public Access, Object Lock not exercised | Create both buckets per §12; scoped IAM keys | **Yes** (provisioning) |
| Email / SMTP | ✅ Executed (STARTTLS sink) | drill phase B; `test_pilot_ops.py`; `email-runbook.md` | register → worker → STARTTLS → message → link followed in 1.6 s; retries 1/5/15 min; failures counted and alerted | No provider; SPF, DKIM and DMARC not published | Provider account, domain verification, DNS records, `mail_check --send-to` | **Yes** |
| Secrets | ✅ Process defined | `secrets-management.md`; start-up guards (`test_pilot_ops.py`) | Production refuses dev or short keys, `*` CORS, http URLs, `@localhost` sender | Data keys cannot be rotated in place (no re-encryption tool) | Generate on the VM, **escrow data keys and the age identity offline** | **Yes** (escrow) |
| Backups | ✅ Executed | `backup.sh`; drill phase D; `backup-restore-runbook.md` | Encrypted dump 2.1 MB at 10k people in 10.2 s, with manifest, checksums and object mirror | Nightly cron and real backup bucket not yet running | Backup bucket with Object Lock; recipient key | **Yes** |
| Restore | ✅ Executed (sandbox) | drill G1–G4; `drill-report.json` | **RTO 75.8 s** disaster → verified; 42 tables / 60,058 rows = manifest; audit append-only; login, property, documents (checksums), GEDCOM export verified; writes after backup absent | Real managed services (PITR, provider snapshots) not drilled; RPO/RTO targets not agreed | Restore drill on real infrastructure; agree targets (proposed RPO ≤ 15 min, RTO ≤ 4 h) | **Yes** |
| Monitoring and alerting | ✅ Implemented | `monitoring-alerting.md`; 18 rules + promtool tests (CI) | Rules tested: 5xx > 5%, DB down, email failures, backup stale/failed, backlog, no workers | Not deployed; no external uptime monitor | Monitoring profile, Alertmanager email, external uptime check, provider alarms | **Yes** |
| Logs and observability | ✅ Verified | `test_observability.py`, `test_pilot_ops.py` | JSON logs from API **and worker**; request IDs; new metrics (DB up, pool, queue, jobs, failures) | **Defects fixed:** worker logs carried email addresses (RQ job descriptions); metrics saw one random worker process | — | No |
| Health checks | ✅ Verified | deploy.sh, drill | Readiness on every replica before smoke; RLS enforced | — | — | No |
| Release, rollback and CI gate | ✅ Executed (sandbox) | `deploy-pilot.yml`, `release-runbook.md`; drill deploys | Deploy 52–59 s incl. pre-deploy backup, migrations, roll, readiness and smoke; automatic app rollback on failure | GitHub environments, reviewers and secrets not configured; `rollback.sh` not exercised on staging | Configure the environments; run a deploy → rollback rehearsal on staging | **Yes** |
| Smoke test | ✅ Executed | `app.cli.smoke` | 13/13 steps in 2.1–3.2 s through TLS, Caddy and ClamAV; verify mode 9/9 after restore | — | Register the smoke account on each environment | **Yes** (setup) |
| Performance | ⚠️ Sandbox only | `performance.md` "Pilot stack in the sandbox"; `evidence/.../perf/` | Through the pilot edge: sequential p95 ≤ **195 ms**; every operation p95 < 500 ms up to **40 req/s** (overall up to 50), 0% errors, 3/3 runs; graceful 503 at 70; imports 1k/10k commit 14 s/165 s; uploads 67/min; property history p95 ≤ 39 ms | Production capacity not certified (shared host); import commit is synchronous (**defect fixed:** proxies cut it off at 120 s) | Staging-host certification; size VM per the memory finding (16 GB for 4 replicas) | **Yes** |
| Accessibility, assistive technology | ⏳ Not run | `manual-test-checklist.md` §4–5 (pilot pack, empty results table) | — | No human pass yet | NVDA+Chrome, VoiceOver+Safari, TalkBack+Chrome (pilot minimum); full matrix for launch | **Yes** (pilot minimum) |
| Hindi review | ⏳ Not reviewed | `docs/localization/hindi-review-checklist.md`, `hindi-review/*.csv` | 1,972 strings extracted, prioritised; 246 flagged for legal review; consistent spelling | No native reviewer yet | Review priorities 1–4 before the pilot, all before launch | **Yes** (p1–4) |
| Legal review (DPDP, Q13) | ⏳ Not started | hindi checklist "Legal review"; privacy model | — | Consent and attestation wording, privacy notice, breach procedure | Counsel review | No for an owner's-circle pilot; **Yes** for other families and public launch |
| Penetration test | ⏳ Prepared | `docs/security/pentest-scope.md` | — | Not performed | Commission an independent tester | No (pilot); **Yes** (public launch) |
| Incident response | ✅ Written | `incident-response.md` (11 scenarios + breach) | — | Not rehearsed | Owner reads it; one tabletop exercise | No |
| Container images | ✅ CI + local | frontend image built here with the repo Dockerfile and served; backend image by CI (Debian mirror blocked here); drill used a test image without Tesseract | — | — | — | No |
| Environment cleanup | ✅ | drill stacks removed (`docker compose down -v`), temp DB dropped, `/etc/hosts` restored | — | — | — | No |

## Defects found and fixed in this pass
Every fix has a regression test that fails without it, or a measured check.

| # | Defect | Found by | Severity | Fix (commit) |
|---|---|---|---|---|
| 1 | **Writes committed after the response was sent.** A client could act on a 201 whose row was not yet visible (404 from another replica), and a failed commit was reported as success, so the data was lost silently | Pipeline benchmark (import commit right after upload → 404) | **High** | `Depends(get_db, scope="function")` (`88ab278`; `test_a_failed_commit_is_an_error_not_a_success`) |
| 2 | **Every deploy after the first failed on managed PostgreSQL:** `ensure_app_role` re-asserted NOSUPERUSER, which needs SUPERUSER | Staging drill (restore → second migrate) | **High** (deployment) | Create once, then verify attributes and ownership (`3dea906`; `test_app_role.py`) |
| 3 | GEDCOM packages over 55 MB (limit 250 MB) refused by nginx with 413 | Infrastructure audit, reproduced with nginx 1.27 | Medium | Import location 260 MB (`16173db`); Caddy limits per route |
| 4 | Import commit of 10,000 people (169 s) cut off by the proxies at 120 s with a 504, although it succeeded | Pipeline benchmark | Medium | 600 s on the import routes (`72f532f`); limitation and trigger recorded |
| 5 | Worker logs carried email recipients and subjects (RQ logs job descriptions with arguments); failed jobs kept them 1 year | Infrastructure audit, reproduced with RQ 2.12 | Medium (privacy) | Name-only descriptions, 7-day failure TTL, `app.cli.worker` (`1d84151`; T31) |
| 6 | Metrics were per process but the API ran `--workers N` behind one port: Prometheus saw one random worker; worker-side failures invisible | Observability audit | Medium (operations) | Single-process replicas scraped individually; Redis-shared job/failure counters (`719cb2a`, ADR-0014) |
| 7 | Production accepted `FORWARDED_ALLOW_IPS=*`, CORS `*`, http public URL, short keys, `@localhost` sender | Audit | Medium (hardening) | Start-up guards (`d260259`; T32) |
| 8 | Object-store errors were unhandled 500s | Audit | Low | Structured 503 + counter + alert (`719cb2a`; T33) |
| 9 | GEDCOM staging failures logged the parser message (can quote family data) | Audit | Low (privacy) | Type + code location only (`719cb2a`) |
| 10 | HTML emails printed the footer twice | Audit | Low | (`5f2ba4e`) |

**Also added:**
- **Email:** retries (1/5/15 min), `mail_check` CLI.
- **Backup and verification tooling:** smoke test, `ops_backup` (manifest, mirror, check-restore),
  `pipeline_bench.py`.

**Tooling issues met while running the drill:**
- scaffolding bugs, listed in `evidence/pilot-2026-10-02/drill-2026-10-02.md`;
- a sandbox limit: the Debian mirror is blocked, so the backend image was built without Tesseract.

## Regression results (final code of this pass)

| Gate | Command | Result |
|---|---|---|
| Backend tests | `uv run pytest` (RLS role) | **345 passed** (312 + 33 new) |
| Backend lint, format, types, SAST | `ruff check`, `ruff format --check`, `mypy app`, `ruff --select S` | clean |
| Python dependencies | `pip-audit` (hashed export) | no known vulnerabilities |
| Migrations | clean DB: upgrade → `alembic check` → downgrade base → upgrade; one head | pass (also a new CI step) |
| Frontend | `npm run lint && npm run typecheck && npm test && npm run build` | pass; 122 tests; OpenAPI types unchanged |
| npm dependencies | `npm audit` (frontend prod, e2e) | 0 vulnerabilities |
| End-to-end | `npx playwright test` | **26/26** |
| Secrets | gitleaks over the full history (78 commits) | 6 findings, all test placeholders (3 known + 3 new fixed test strings in `test_pilot_ops.py`) |
| Deploy configuration | pilot compose render (all profiles), `caddy validate`, `promtool check rules` + `test rules`, shellcheck, actionlint | all pass |
| Docker | `docker compose config` (both); frontend image from the repo Dockerfile, served 200 | pass; backend image: CI (Debian mirror blocked in the sandbox) |
| Pilot stack | staging drill; edge test; performance through the stack | pass (see matrix) |
| DAST | not re-run in this pass (no HTTP surface change beyond error codes and limits); the GitHub run is still pending | — |

## Remaining items

**Blockers for the controlled pilot.** All are human actions or external dependencies (go-live
checklist, Blocking):
1. Provider and account decision; VM, managed PostgreSQL, buckets provisioned (ADR-0014).
2. DNS and TLS certificate; client-IP check on the VM.
3. SMTP provider, sender domain verification, SPF/DKIM/DMARC; end-to-end email test.
4. Secrets filled in; **data keys and the age identity escrowed offline**.
5. GitHub `staging`/`pilot` environments with reviewers and deploy secrets; first gated deploy.
6. Nightly backup running; **restore drill on real infrastructure**; PITR test; RPO/RTO agreed.
7. Monitoring profile, Alertmanager route test, external uptime monitor, provider alarms.
8. Performance certification on the staging VM (generator on another machine).
9. Screen-reader pilot minimum (NVDA+Chrome, VoiceOver+Safari, TalkBack+Chrome).
10. Native-Hindi review of priorities 1–4.
11. Pilot privacy notice, and owner approval of who is invited. Legal review first if families
    outside the owner's circle are invited.

**Human actions** (beyond the blockers): read the incident runbook and run one tabletop exercise;
register the smoke account per environment; rehearse rollback on staging.

**External dependencies:**
- **Cloud and email providers:** account, region, sandbox exit, quotas.
- **Google OAuth** (optional): client per environment, consent screen.
- **Docker Hub:** rate limits on CI image pulls.
- **Counsel** (DPDP).
- **An independent penetration tester.**

**Deferred / non-blocking:**
- data-key rotation tool (a public-launch item);
- background import commits (trigger: imports above ~20,000 people);
- log shipping, OpenTelemetry tracing, dashboards, TLS-expiry probe;
- image signing and SBOMs;
- a second VM / HA (public-launch decision);
- a people-list index (trigger: trees of ~100k people);
- the onboarding test that failed once under load on 1 Oct (not seen since).

---

# Post-Phase-8 production-readiness validation (1 Oct 2026)

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
| Container images | ✅ Pass | frontend image built locally and served in DAST; **both images built by CI** (`docker` job, run 36922828365, on this PR's head `dc6a5eb`) | backend and frontend `docker build` succeeded; `docker compose config` valid | The backend image could not be built in the sandbox (egress policy, rate limit); CI is the evidence | — | No |
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
| Docker | `docker compose config -q`; `docker build` backend and frontend | ✅ both images built by CI (run 36922828365); frontend also built locally |

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
