# Environment variables

Every setting the application reads, from `backend/app/core/config.py` (prefix `VSH_`), plus the
deployment-level variables of the pilot stack (`deploy/pilot`). See ADR-0014 for the topology and
`docs/security/secrets-management.md` for how secrets are supplied, rotated and revoked.

**Where each value lives on the pilot VM:**

| File | Read by | Mode | Holds |
|---|---|---|---|
| `/etc/vanshavali/compose.env` | `docker compose` (interpolation) | 644 | non-secret stack settings: image, domain, TLS contact, replicas |
| `/etc/vanshavali/app.env` | backend, worker, tools | 600 | app secrets and service endpoints |
| `/etc/vanshavali/migrate.env` | migrate (release step), backups | 600 | schema-owner DB URL, app-role password |
| `/etc/vanshavali/backup.env` | backup/restore scripts | 600 | backup bucket, age public key |
| `/etc/vanshavali/smoke.env` | smoke test | 600 | the smoke-test account |
| `deploy/pilot/compose.yml` (`environment:`) | backend, worker | in git | values that must be identical everywhere (production mode, TLS cookies, proxy trust) |

**How to read the tables:**
- **Req.** = required in production. "fixed" means `compose.yml` sets the value and you must not
  override it.
- **Sensitive** = treat as a secret: never in git, logs, tickets or chat.
- Examples with placeholders are in `deploy/pilot/env/*.env.example`.
- The app **refuses to start in production** with unsafe values. The rules are in
  `Settings.validate_production`, tested in `test_pilot_ops.py` and `test_email_auth.py`.

## Core

| Variable | Purpose | Req. | Development default | Production recommendation | Sensitive |
|---|---|---|---|---|---|
| `VSH_ENV` | `development`, `test` or `production`; production turns on the start-up guards | fixed | `development` | `production` (compose.yml) | no |
| `VSH_PUBLIC_BASE_URL` | Origin users reach: email links, Google redirect default, download links | fixed | `http://localhost:3000` | `https://<VSH_DOMAIN>` (compose.yml); **must be https** | no |
| `VSH_DOMAIN` | Public host name (Caddy site, certificate, `VSH_PUBLIC_BASE_URL`, CORS) | yes | — | e.g. `pilot.example.org` (compose.env) | no |
| `VSH_API_PREFIX` | API path prefix | no | `/api/v1` | leave | no |
| `VSH_DATABASE_URL` | PostgreSQL URL. **App/worker: the non-owner role** (RLS applies). Migrate: the owner | yes | local `vanshavali` | `postgresql+psycopg://vanshavali_app:…@<host>:5432/vanshavali?sslmode=verify-full&sslrootcert=<CA file>` | **yes** (password) |
| `VSH_REDIS_URL` | Job queue and rate-limit counters | fixed | `redis://localhost:6379/0` | `redis://redis:6379/0` (VM-local container) | no |
| `VSH_STATEMENT_TIMEOUT_MS` | Per-statement timeout for app connections | no | `15000` | leave | no |
| `VSH_DB_POOL_SIZE` / `VSH_DB_MAX_OVERFLOW` | Connections per backend process | no | `5` / `10` | keep `replicas × (size + overflow)` + workers + headroom under the DB's `max_connections` | no |
| `VSH_DB_POOL_TIMEOUT_S` | Wait for a pooled connection before a 503 | no | `5.0` | leave | no |
| `VSH_MAX_INFLIGHT_REQUESTS` / `VSH_ADMISSION_WAIT_S` | Admission control per process (0 = pool size + overflow) | no | `0` / `1.0` | leave; alert `LoadShedding` tells you to add replicas | no |
| `IMAGE_PREFIX` / `VSH_VERSION` | Container images (`<prefix>/vanshavali-backend:<version>`) | yes | — | `ghcr.io/<owner>`; the version is the commit SHA, set by `deploy.sh` | no |
| `BACKEND_REPLICAS` / `WORKER_REPLICAS` | One uvicorn process per backend replica; worker replicas = OCR/email concurrency | no | `2` / `1` | 2–4 / 1–2 for the pilot (VM sizing in the pilot plan) | no |

## Security

| Variable | Purpose | Req. | Development default | Production recommendation | Sensitive |
|---|---|---|---|---|---|
| `VSH_SIGNING_KEY` | HMAC key for signed download links (and other signed tokens) | yes | dev constant (refused in production) | ≥ 32 random characters (`openssl rand -hex 32`) | **yes** |
| `VSH_STANDARD_DATA_KEY` | AES-256-GCM key for STANDARD documents (ADR-0004) | yes | dev constant (refused) | 32 random bytes, base64; **escrow it** | **yes** |
| `VSH_VAULT_DATA_KEY` | AES-256-GCM key for VAULT documents (birth certificates, property papers…) | yes | dev constant (refused) | 32 random bytes, base64, different from STANDARD; **escrow it** | **yes** |
| `VSH_COOKIE_SECURE` | `Secure` cookies + HSTS from the API | fixed | `false` | `true` (compose.yml; refused otherwise) | no |
| `VSH_SESSION_IDLE_DAYS` / `VSH_SESSION_ABSOLUTE_DAYS` | Server-side session lifetimes (ADR-0005) | no | `14` / `30` | leave | no |
| `VSH_SESSION_COOKIE_NAME`, `VSH_CSRF_COOKIE_NAME`, `VSH_CSRF_HEADER_NAME` | Session cookie and double-submit CSRF names (the SPA sends the header) | no | `vsh_session`, `vsh_csrf`, `X-CSRF-Token` | leave (the SPA expects these) | no |
| `VSH_CORS_ORIGINS` | JSON list of allowed browser origins | fixed | `["http://localhost:3000"]` | `["https://<VSH_DOMAIN>"]` (compose.yml); `*` refused | no |
| `FORWARDED_ALLOW_IPS` | Proxies whose `X-Forwarded-For` uvicorn trusts (client IP for rate limits, audit, sessions; threat T30). **No `VSH_` prefix**: uvicorn reads it | fixed | `127.0.0.1` (image: `127.0.0.1,::1`) | exactly the Caddy address `172.30.0.10` (compose.yml). `*` or a `/0` network is refused at start-up; loopback-only logs a warning | no |
| `VSH_LOGIN_RATE_LIMIT_PER_MINUTE` | Per-IP and per-account login throttle | no | `10` | leave | no |
| `VSH_REGISTER_RATE_LIMIT_PER_MINUTE` | Per-IP account registrations per minute (per-email: 5/hour, fixed) | no | `20` | leave | no |
| `VSH_TOKEN_RATE_LIMIT_PER_MINUTE` | Per-IP uses of emailed tokens (verify email, confirm password reset; one shared bucket) per minute. Raised only by the E2E harness | no | `30` | leave (never raise in production) | no |
| `VSH_RATE_LIMIT_BACKEND` | `memory` or `redis` (shared by all replicas) | fixed | `memory` | `redis` (compose.yml) | no |
| Trusted hosts | No app-level setting: Caddy serves only `VSH_DOMAIN` (any other Host/SNI gets no certificate and no site), and the API is not published | — | — | — | — |
| Password hashing | Argon2id with argon2-cffi's defaults (ADR-0005); **not configurable by environment** | — | — | — | — |
| `VSH_METRICS_TOKEN` | Bearer token for `GET /api/v1/metrics` (empty = endpoint off) | yes (for monitoring) | empty | 32+ random characters; same value in `/etc/vanshavali/metrics_token` for Prometheus | **yes** (low impact: read-only operational counters) |

## Sign in with Google (ADR-0012)

| Variable | Purpose | Req. | Development default | Production recommendation | Sensitive |
|---|---|---|---|---|---|
| `VSH_GOOGLE_CLIENT_ID` | OAuth client ID ("Web application" type) | no (feature off when empty) | empty | the pilot's own client; **separate client per environment** | no (public, but keep with config) |
| `VSH_GOOGLE_CLIENT_SECRET` | OAuth client secret | with the ID | empty | from Google Cloud; rotate per secrets-management.md | **yes** |
| `VSH_GOOGLE_REDIRECT_URI` | Redirect URI; must match Google's registration exactly | no | `<public base>/api/v1/auth/google/callback` | leave empty (derived); must be https (refused otherwise) | no |
| `VSH_GOOGLE_AUTHORIZE_URL`, `VSH_GOOGLE_TOKEN_URL`, `VSH_OIDC_STATE_TTL_SECONDS` | Endpoints and state lifetime | no | Google's endpoints, `600` | leave | no |

## SMTP (ADR-0005; `docs/operations/email-runbook.md`)

| Variable | Purpose | Req. | Development default | Production recommendation | Sensitive |
|---|---|---|---|---|---|
| `VSH_MAIL_BACKEND` | `console`, `file` or `smtp` | fixed | `console` | `smtp` (compose.yml; the others are refused) | no |
| `VSH_SMTP_HOST` / `VSH_SMTP_PORT` | Submission server | yes | — / `587` | provider's submission endpoint, port 587 | no |
| `VSH_SMTP_USER` / `VSH_SMTP_PASSWORD` | SMTP credentials (sent only after STARTTLS) | yes | — | provider SMTP credentials scoped to sending | **yes** (password) |
| `VSH_SMTP_STARTTLS` | Upgrade with STARTTLS and verify the certificate | yes | `true` | `true` (false refused in production). Implicit TLS on 465 is not supported | no |
| `VSH_SMTP_TIMEOUT_SECONDS` | Connect/command timeout | no | `20` | leave | no |
| `VSH_MAIL_FROM` | From header, e.g. `Vanshavali <no-reply@example.org>` | yes | `…@localhost` (refused) | an address on a domain with SPF, DKIM and DMARC | no |
| `VSH_EMAIL_VERIFY_TTL_HOURS` / `VSH_PASSWORD_RESET_TTL_MINUTES` | Link lifetimes | no | `48` / `60` | leave | no |
| `VSH_MAIL_FILE_DIR` | Output directory of the `file` backend (tests/E2E only) | no | `./var/mail` | unused | no |

## Storage (ADR-0004)

| Variable | Purpose | Req. | Development default | Production recommendation | Sensitive |
|---|---|---|---|---|---|
| `VSH_STORAGE_BACKEND` | `local` or `s3` | fixed | `local` | `s3` (compose.yml) | no |
| `VSH_S3_ENDPOINT_URL` | S3 API endpoint | no | none | empty for AWS S3; the provider's endpoint for S3-compatible stores | no |
| `VSH_S3_REGION` | Bucket region | yes | `ap-south-1` | the Indian region of the bucket | no |
| `VSH_S3_BUCKET` | Private document bucket | yes | `vanshavali` | e.g. `vanshavali-pilot-documents` (Block Public Access, versioning, default encryption) | no |
| `VSH_S3_ACCESS_KEY` / `VSH_S3_SECRET_KEY` | Credentials limited to this bucket (Get/Put/Delete/List + version ops for the purge) | yes | none | a dedicated IAM user/key per environment | **yes** |
| `VSH_DOWNLOAD_URL_TTL_SECONDS` | Lifetime of signed download links (served by the API, never a public bucket URL) | no | `300` | leave (5 minutes) | no |
| `VSH_DOCUMENT_PURGE_AFTER_DAYS` | Soft-deleted documents restorable this long, then purged by the daily job | no | `30` | leave; keep bucket retention locks shorter than this (ADR-0004) | no |
| `VSH_MAX_UPLOAD_BYTES` | Per-file upload limit | no | 50 MB | leave; Caddy allows 55 MB (`Caddyfile`) | no |
| `VSH_MAX_GEDCOM_PACKAGE_BYTES` | GEDCOM zip/GEDZIP limit | no | 250 MB | leave; Caddy and nginx allow 260 MB on `/imports` | no |
| `VSH_MAX_PDF_PAGES`, `VSH_MAX_IMAGE_PIXELS` | Decompression-bomb limits | no | `300`, `80000000` | leave | no |
| `VSH_STORAGE_LOCAL_PATH` | Directory of the `local` backend | no | `./var/storage` | unused in production | no |
| `BACKUP_S3_*` (`ENDPOINT_URL`, `REGION`, `BUCKET`, `ACCESS_KEY`, `SECRET_KEY`) | Backup bucket for dumps and the object mirror (backup.env) | yes | — | a separate bucket with Object Lock; credentials **without delete** | **yes** (keys) |
| `BACKUP_AGE_RECIPIENT` | age public key the dumps are encrypted to | yes | — | the identity (private key) stays offline | no (public key) |
| `BACKUP_HEARTBEAT_URL`, `BACKUP_LOCAL_KEEP_DAYS` | Dead-man's switch URL; local retention | no | empty, `7` | an external heartbeat monitor | low (URL is a capability) |

## Malware scanning, OCR and jobs

| Variable | Purpose | Req. | Development default | Production recommendation | Sensitive |
|---|---|---|---|---|---|
| `VSH_SCANNER` | `clamd` or `eicar_test` (tests only) | fixed | `eicar_test` | `clamd` (compose.yml; refused otherwise) | no |
| `VSH_CLAMD_HOST` / `VSH_CLAMD_PORT` | clamd address | fixed | `localhost` / `3310` | `clamav` / `3310` (compose.yml) | no |
| `VSH_JOB_MODE` | `sync` (inline) or `rq` | fixed | `sync` | `rq` (compose.yml) | no |
| `VSH_JOB_QUEUE_NAME` | RQ queue | no | `vanshavali` | leave | no |
| `VSH_OCR_ENABLED` | OCR + extraction proposals for scans | no | `true` | `true` | no |
| `VSH_TESSERACT_CMD`, `VSH_TESSERACT_LANGUAGES` | Tesseract binary and languages | no | `tesseract`, `eng+hin` | leave (the image ships eng+hin) | no |
| `OMP_THREAD_LIMIT` | Threads per tesseract process (no prefix) | no | `1` | leave at 1; scale OCR with `WORKER_REPLICAS` (performance.md) | no |
| Worker concurrency | One job at a time per worker container | — | — | `WORKER_REPLICAS` | — |
| `VSH_MAX_TRAVERSAL_DEPTH` | Ancestor/descendant query depth cap | no | `25` | leave | no |
| `VSH_GEDCOM_EXT_BASE_URI` | URI of the Indian GEDCOM extensions | no | project URI | leave | no |

## Monitoring and logs

| Variable | Purpose | Req. | Development default | Production recommendation | Sensitive |
|---|---|---|---|---|---|
| `VSH_LOG_FORMAT` | `json` or `text` | fixed | `text` | `json` (compose.yml) | no |
| `VSH_LOG_LEVEL` | Root log level | no | `INFO` | `INFO` (`DEBUG` never in production: libraries may log payloads) | no |
| `VSH_METRICS_TOKEN` | see Security | yes | — | — | yes |
| Error-reporting DSN (Sentry etc.) | **Not supported** by the code; errors go to the JSON logs and the 5xx alerts. Adding one is a privacy decision (payload scrubbing) for a later ADR | — | — | — | — |
| `VSH_TLS` | Caddy: ACME contact email (production) or `internal` (drills without DNS) | yes | — | the operations mailbox | no |

## Deployment-only (scripts)

| Variable | Purpose |
|---|---|
| `VSH_CONFIG_DIR` / `VSH_STATE_DIR` | Config and state directories (default `/etc/vanshavali`, `/var/lib/vanshavali`) |
| `VSH_APP_DB_ROLE` / `VSH_APP_DB_PASSWORD` | migrate.env: the role `ensure_app_role` creates/updates; must match app.env's URL |
| `SMOKE_EMAIL` / `SMOKE_PASSWORD` | smoke.env: dedicated smoke-test account (sensitive: password) |
| `SKIP_BACKUP`, `SKIP_SMOKE`, `SKIP_PULL`, `NO_AUTO_ROLLBACK` | `deploy.sh` switches (see the release runbook) |
| `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS` | GitHub environment secrets for `deploy-pilot.yml` |

## Rules
- `.env`, `*.env` and `.env.*` are git-ignored; only `*.env.example` files are tracked, and those
  hold placeholders (`CHANGE_ME`) only. `gitleaks` runs over the history (production-readiness report).
- Never pass a secret on a command line: process listings and shell history keep it. The scripts
  read files or environment variables. `pg_dump` gets its password through `PGPASSWORD` passed by
  name, never inside a URL argument.
- The app never logs settings. `mail_check` prints `password=set|not set`, never the value.
