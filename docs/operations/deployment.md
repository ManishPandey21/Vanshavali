# Deployment

## Local (docker compose)
```bash
cp .env.example .env   # fill in the keys
docker compose up --build
# app: http://localhost:8080   API docs: http://localhost:8000/api/v1/docs   MinIO console: :9001
docker compose run --rm backend python -m app.cli.seed_demo   # optional demo family
```
Services: postgres, redis, minio (+ bucket init with versioning), clamav (clamd), migrate (a one-off
`alembic upgrade head` as the schema owner, then `app.cli.ensure_app_role`), backend (FastAPI), worker (RQ: scanning, previews, OCR, extraction), and
frontend (nginx serving the SPA and proxying `/api`).

## Production shape (ASSUMPTION until the hosting decision, implementation-plan §12)
- Managed PostgreSQL 16 with PITR, managed Redis, S3 with SSE-KMS plus versioning and object lock,
  and clamd as a sidecar or internal service.
- Containers: `backend` (N replicas behind TLS load balancer), `worker` (M replicas), `frontend`
  (nginx or CDN).
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
  See ADR-0004 §7.
- **Frontend security headers:** they live in `frontend/nginx-security-headers.conf`, which is
  included at server level *and* in every `location` that has its own `add_header`. nginx does not
  inherit `add_header` into such locations. Keep that rule when adding locations; the weekly DAST
  run fails if CSP, X-Frame-Options or nosniff disappear.

## Scheduled operational workflows (not on pull requests)
| Workflow | Trigger | What it does |
|---|---|---|
| `.github/workflows/dast.yml` | weekly (Mon 04:23 UTC) and manual | Runs these steps:<ul><li>Postgres and Redis services, migrate, seed demo</li><li>uvicorn</li><li>SPA via the production nginx image</li><li>ZAP baseline on `http://localhost:8080/`</li><li>ZAP API scan on `/api/v1/openapi.json`, authenticated as the demo user</li></ul>Rules are in `.zap/rules.tsv` and reports are uploaded as artefacts (`zap-baseline`, `zap-api-scan`). Kept off PRs to avoid flaky merges. **Not yet executed** (written without a Docker daemon). |
| `.github/workflows/drill.yml` | nightly (02:41 UTC) and manual (`people`, `encryption` inputs) | Backup/restore drill `ops/backup/drill.sh`: encrypted dump, fresh restore, `alembic upgrade head`, `verify.py`. Timings go to the job summary; see `backup-restore.md`. |

HTTP load test (manual, not in CI): `ops/loadtest/run.sh` seeds 10k people and runs
`uvicorn --workers 4` against 20 and 50 virtual users. See `performance.md`.
