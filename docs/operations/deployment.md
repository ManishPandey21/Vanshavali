# Deployment

## Local (docker compose)
```bash
cp .env.example .env   # fill in the keys
docker compose up --build
# app: http://localhost:8080   API docs: http://localhost:8000/api/v1/docs   MinIO console: :9001
docker compose run --rm backend python -m app.cli.seed_demo   # optional demo family
```
Services: postgres, redis, minio (+ bucket init with versioning), clamav (clamd), migrate (a one-off
`alembic upgrade head`), backend (FastAPI), worker (RQ: scanning, previews, OCR, extraction), and
frontend (nginx serving the SPA and proxying `/api`).

## Production shape (ASSUMPTION until the hosting decision, implementation-plan §12)
- Managed PostgreSQL 16 with PITR, managed Redis, S3 with SSE-KMS plus versioning and object lock,
  and clamd as a sidecar or internal service.
- Containers: `backend` (N replicas behind TLS load balancer), `worker` (M replicas), `frontend`
  (nginx or CDN).
- Required settings: `VSH_ENV=production` (the app refuses to start with dev keys, the EICAR test
  scanner, or insecure cookies), `VSH_COOKIE_SECURE=true`, keys from a secret manager, and
  `VSH_CORS_ORIGINS` set to the real origin.
- Release: build images → run `alembic upgrade head` as a one-off task → roll backend and worker.
  Migrations must be backward compatible with the previous app version (expand/contract).
- TLS 1.2+ terminates at the load balancer. HSTS is set by the API when `VSH_COOKIE_SECURE=true`.
- Observability (DEFERRED Phase 8): structured JSON logs, request IDs, OpenTelemetry traces, and
  alerts on 5xx, job failures and scanner unavailability.
