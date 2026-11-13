# Deployment

## Local (docker compose)
```bash
cp .env.example .env   # fill in the keys
docker compose up --build
# app: http://localhost:8080   API docs: http://localhost:8000/api/v1/docs   MinIO console: :9001
# optional demo family + dev accounts (export VSH_DEMO_PASSWORD and VSH_SUPERADMIN_PASSWORD first)
docker compose run --rm -e VSH_DEMO_PASSWORD -e VSH_SUPERADMIN_PASSWORD backend python -m app.cli.seed_demo
```
Seeded accounts and their rules: `docs/operations/dev-accounts.md` (refused outside development/test).

**Email.** By default the local stack uses the `console` mailer: backend and worker logs show each
message, with its link in development, and nothing is sent. Compose passes the mail settings from
`.env` to the backend and worker.

To catch real messages locally, use the bundled **Mailpit** (profile `mail`). It accepts every
message, delivers none, and shows them at http://localhost:8025 (published on loopback only). Set
in `.env`:

```bash
COMPOSE_PROFILES=mail
VSH_MAIL_BACKEND=smtp
VSH_SMTP_HOST=mailpit
VSH_SMTP_PORT=1025
VSH_SMTP_STARTTLS=false
```
Then run `docker compose up -d`, sign up at http://localhost:8080, and open the confirmation email in
Mailpit.

To deliver through a real provider instead:

```bash
VSH_MAIL_BACKEND=smtp
VSH_MAIL_FROM=Vanshavali <no-reply@your-domain.example>
VSH_SMTP_HOST=smtp.your-provider.example
VSH_SMTP_PORT=587
VSH_SMTP_USER=...
VSH_SMTP_PASSWORD='...'      # single-quote it if it contains $
VSH_SMTP_STARTTLS=true
```
After changing these, recreate the containers (`docker compose up -d backend worker`) and check with
`docker compose run --rm backend python -m app.cli.mail_check --send-to you@example.org`.
`host.docker.internal` also resolves inside the backend and worker, for a catcher on the host.
Services: postgres, redis, minio (+ bucket init with versioning), clamav (clamd), mailpit (opt-in, profile `mail`), migrate (a one-off
`alembic upgrade head` as the schema owner, then `app.cli.masterdata load` (master-data vocabulary packs, ADR-0018; idempotent) and `app.cli.ensure_app_role`), backend (FastAPI), worker (RQ: scanning, previews, OCR, extraction), and
frontend (nginx serving the SPA and proxying `/api`).

## Production shape
**Decided for the pilot: ADR-0014.** One VM runs `deploy/pilot/compose.yml` (Caddy, the nginx SPA,
backend replicas, worker, Redis, clamd, monitoring), with managed PostgreSQL 16 (PITR) and private
S3 in an Indian region. Read these alongside this section:
- `docs/deployment/pilot-deployment-plan.md` (architecture, provisioning, storage and DB setup);
- `docs/deployment/environment-variables.md` (every setting);
- `docs/operations/release-runbook.md` (deploy and rollback);
- `docs/operations/backup-restore-runbook.md`;
- `docs/operations/monitoring-alerting.md`;
- `docs/operations/incident-response.md`.

The general rules below still apply to any topology:
- Containers: `backend` (one uvicorn process per replica, behind the TLS proxy), `worker`
  (`python -m app.cli.worker`, M replicas), `frontend` (nginx).
- Required settings: `VSH_ENV=production` (the app refuses to start with dev keys, the EICAR test
  scanner, or insecure cookies), `VSH_COOKIE_SECURE=true`, keys from a secret manager, and
  `VSH_CORS_ORIGINS` set to the real origin.
- **Two database roles.** Migrations run as the schema owner. The backend and worker connect as
  `vanshavali_app` (`NOSUPERUSER NOBYPASSRLS`, not the owner), so row-level security applies to them
  (ADR-0002 §7). Never point `VSH_DATABASE_URL` for the API or workers at the owner or a superuser.
  `/health/ready` reports `rls: false` if you do.
- Release: build images → run `alembic upgrade head` as the owner → run
  `python -m app.cli.ensure_app_role` (idempotent; takes `VSH_APP_DB_ROLE` and
  `VSH_APP_DB_PASSWORD`) → roll backend and worker.
  Migrations must be backward compatible with the previous app version (expand/contract).
- **Capacity and overload.** Per backend worker process:
  - The DB pool is `VSH_DB_POOL_SIZE` (5) + `VSH_DB_MAX_OVERFLOW` (10) connections. Keep
    workers × (size + overflow) under PostgreSQL's `max_connections`, with headroom for migrations
    and admin. For example, 4 workers × 15 = 60 against the default of 100.
  - Admission control admits at most `VSH_MAX_INFLIGHT_REQUESTS` API requests at once (0 = pool
    size + overflow). Excess requests wait up to `VSH_ADMISSION_WAIT_S` (1 s), then get **503
    `server_busy` with `Retry-After: 2`**.
  - A pool wait longer than `VSH_DB_POOL_TIMEOUT_S` (5 s) is also a 503, never a hang.
  - Health, readiness and metrics are never shed, so probes keep working under load.
  - Alert on a sustained 5xx rate with `server_busy` in the logs (`app.admission` warnings): it
    means the node is at capacity and needs another replica. Capacity figures are in
    `docs/operations/performance.md`.
- **Client IP behind proxies.** Set `FORWARDED_ALLOW_IPS` on the backend to the exact addresses or
  CIDRs of the reverse proxies directly in front of it: the nginx tier and the load balancer. The
  image defaults to loopback only. Never use `*` or a subnet that also contains clients (for
  example a Docker bridge, whose gateway is how host-published ports reach nginx): a client could
  then choose its own IP, dodge per-IP rate limits and falsify audit and session IPs (threat T30).
  Compose pins nginx to `172.28.0.10` and trusts only that address.
- TLS 1.2+ terminates at the load balancer. HSTS is set by the API when `VSH_COOKIE_SECURE=true`.
- **Observability.**
  - Set `VSH_LOG_FORMAT=json`: one JSON object per line, with `request_id`, `method`, `route`,
    `status` and `duration_ms`.
  - Every response carries `X-Request-ID`. A well-formed ID from the load balancer is kept.
  - Access logs record the **route template**, never the raw path or query string (signed download
    tokens travel in query strings). Uvicorn's own access log is off (`--no-access-log`).
  - Probes: `GET /api/v1/health` is liveness and touches no dependency. `GET /api/v1/health/ready`
    checks the database, Redis (when used) and **RLS in force**. In production it answers 503 if the
    app role bypasses RLS.
  - `GET /api/v1/metrics` serves Prometheus text when `VSH_METRICS_TOKEN` is set. Scrape it with
    `Authorization: Bearer <token>`; without a token configured it answers 404. Metrics are per
    process, so scrape each replica.
  - Every API and worker statement is capped by `VSH_STATEMENT_TIMEOUT_MS` (default 15 s).
  - Suggested alerts: 5xx rate, p95 latency per route, readiness failures, `document.*_failed`
    job errors in logs, and the scanner being unavailable.
  - OpenTelemetry tracing is DEFERRED.
- **Scheduled maintenance (daily)**, as the app role:
  `python -m app.cli.maintenance purge-deleted-documents`, then
  `python -m app.cli.maintenance sweep-orphans` (a report; add `--delete` once you have reviewed it).
  See ADR-0004 §7. Also daily: `purge-sign-in-records` and `scrub-audit-network` (ADR-0033: sign-in
  records and audit IP/browser are kept for one year).
- **Frontend security headers:** they live in `frontend/nginx-security-headers.conf`, which is
  included at server level *and* in every `location` that has its own `add_header`. nginx does not
  inherit `add_header` into such locations. Keep that rule when adding locations; the weekly DAST
  run fails if CSP, X-Frame-Options or nosniff disappear.

## Scheduled operational workflows (not on pull requests)
| Workflow | Trigger | What it does |
|---|---|---|
| `.github/workflows/dast.yml` | weekly (Mon 04:23 UTC) and manual | Runs these steps:<ul><li>Postgres and Redis services, migrate, seed demo</li><li>uvicorn</li><li>SPA via the production nginx image</li><li>ZAP baseline on `http://localhost:8080/`</li><li>ZAP API scan on `/api/v1/openapi.json`, authenticated as the demo user</li></ul>Rules are in `.zap/rules.tsv` and reports are uploaded as artefacts (`zap-baseline`, `zap-api-scan`). Kept off PRs to avoid flaky merges. **Not yet executed** (written without a Docker daemon). |
| `.github/workflows/deploy-pilot.yml` | manual (`main` only) | The deployment gate: full CI on the commit → images tagged with the SHA → approval of the protected `staging`/`pilot` environment → `deploy.sh` over SSH (release-runbook.md) |
| `.github/workflows/drill.yml` | nightly (02:41 UTC) and manual (`people`, `encryption` inputs) | Backup/restore drill `ops/backup/drill.sh`: encrypted dump, fresh restore, `alembic upgrade head`, `verify.py`. Timings go to the job summary; see `backup-restore.md`. |

HTTP load test (manual, not in CI): `ops/loadtest/run.sh` seeds 10k people and runs
`uvicorn --workers 4` against 20 and 50 virtual users. See `performance.md`.
