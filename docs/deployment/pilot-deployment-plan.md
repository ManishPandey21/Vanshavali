# Pilot deployment plan

**Goal:** move Vanshavali from "production-pilot ready" (`docs/release/production-readiness.md`,
1 Oct 2026) to a deployable, observable and recoverable **staging** environment and **controlled
pilot**. The pilot is a few invited families; it is not a public launch.

**Decision record:** ADR-0014. It chooses one VM running Docker Compose, managed PostgreSQL and
S3, in an Indian region. Kubernetes and multi-region are not needed at this scale (triggers in
`docs/architecture/implementation-plan.md` §12).

**What is in the repository:**

| Piece | Path |
|---|---|
| Stack definition | `deploy/pilot/compose.yml` (+ `Caddyfile`) |
| Host setup | `deploy/pilot/scripts/bootstrap-host.sh` |
| Release / rollback | `deploy/pilot/scripts/deploy.sh`, `rollback.sh`, `.github/workflows/deploy-pilot.yml` |
| Backup / restore | `deploy/pilot/scripts/backup.sh`, `restore.sh`, `backend/app/cli/ops_backup.py` |
| Smoke test | `backend/app/cli/smoke.py` |
| Monitoring | `deploy/pilot/monitoring/` (Prometheus, alert rules + tests, Alertmanager example) |
| Config templates | `deploy/pilot/env/*.env.example` |
| Staging drill | `deploy/pilot/drill/` (stand-ins for managed services; runs the real stack end to end) |

## 1. Target architecture

```
                       Internet (HTTPS only; 80 redirects)
                                    │
                         DNS  pilot.example.org  A → VM
                                    │
┌──────────────────────────── VM (Ubuntu 24.04, Indian region) ─────────────────────────────┐
│  ufw: 22 (admin CIDR), 80, 443                                                            │
│                                                                                           │
│  caddy 172.30.0.10 ── TLS (ACME), HSTS, body limits (55 MB / 260 MB imports)              │
│     ├── /api/*  ──► backend ×N   (uvicorn, 1 process each; FORWARDED_ALLOW_IPS=172.30.0.10)│
│     └── /*      ──► frontend     (nginx: SPA, CSP, security headers)                      │
│                                                                                           │
│  worker ×M (RQ: scan → previews → OCR → extraction; email)                                │
│  redis (AOF volume: queue, rate limits)       clamav (signatures volume)                  │
│  prometheus · alertmanager · node-exporter    (profile "monitoring", loopback-only UIs)   │
│  cron: nightly backup.sh · daily purge · weekly orphan report · image prune               │
└──────────────┬───────────────────────────────────────┬────────────────────────────────────┘
               │ TLS (verify-full), private network     │ HTTPS (S3 API)
   ┌───────────▼───────────┐                ┌──────────▼───────────┐   ┌──────────────────────┐
   │ Managed PostgreSQL 16 │                │ S3 document bucket   │   │ S3 backup bucket     │
   │ PITR, automated backup│                │ private, versioned,  │   │ separate account,    │
   │ app role = RLS-bound  │                │ SSE; objects already │   │ Object Lock; dumps   │
   │ owner = migrations    │                │ AES-GCM by the app   │   │ (age) + object mirror│
   └───────────────────────┘                └──────────────────────┘   └──────────────────────┘
   SMTP provider (STARTTLS 587; SPF/DKIM/DMARC) · Google OAuth (optional) · GHCR (images)
```

| Concern | Choice | Notes |
|---|---|---|
| Frontend hosting | The nginx image (`frontend/`) behind Caddy on the VM | Static SPA. A CDN is unnecessary for the pilot; the CSP is `'self'`-only and assets are hashed and immutable |
| Backend hosting | `backend` replicas on the VM (`BACKEND_REPLICAS`, default 2) | One process per container, so Prometheus scrapes each; Caddy re-resolves the replicas every 5 s |
| Workers | `worker` replicas (`WORKER_REPLICAS`, default 1) | One job at a time each; OCR is single-threaded (`OMP_THREAD_LIMIT=1`) |
| PostgreSQL | Managed, 16.x, smallest production class with PITR | Separate owner and app roles (ADR-0002 §7); TLS `verify-full` |
| Redis | Container on the VM with AOF | Holds the queue and counters only; no canonical data |
| Object storage | Managed S3, private | Plus a backup bucket in a separate account (section 12) |
| Reverse proxy | Caddy 2.10 | The only published service |
| TLS | Let's Encrypt via Caddy (automatic issuance and renewal) | Section 10 |
| DNS | A records only for pilot and staging names | No AAAA unless Docker IPv6 is configured (client IPs) |
| SMTP | Transactional provider in the region (e.g. SES ap-south-1) | `docs/operations/email-runbook.md` |
| Secrets | Files in `/etc/vanshavali` (mode 600) plus the owner's password manager | `docs/security/secrets-management.md` |
| Backups | Managed PITR plus nightly encrypted `pg_dump` and object mirror to the backup bucket | `docs/operations/backup-restore-runbook.md` |
| Monitoring and alerts | Prometheus + Alertmanager on the VM, plus an external uptime monitor and provider alarms | `docs/operations/monitoring-alerting.md` |
| Logs | JSON to stdout, Docker rotation (20 MB × 5) | Shipping to a log service is "Recommended" |
| Health checks | `/api/v1/health` (liveness, Docker), `/api/v1/health/ready` (DB, Redis, RLS) | deploy.sh waits for readiness on every replica |

## 2. Environments: staging vs pilot

| | Staging | Pilot |
|---|---|---|
| Purpose | Every release first; restore drills; performance certification; penetration test | Invited families |
| Data | Synthetic only (smoke trees, `seed_demo`, synthetic 10k tree). **Never real family data** | Real |
| VM | Smaller is fine (2–4 vCPU / 8 GB) | 4 vCPU / 8 GB with the default 2 backend replicas + 1 worker; **16 GB for 4 replicas** (each backend process measured at 560–780 MiB under load, ClamAV ~1 GB) |
| Database / buckets | Own instance and buckets | Own instance and buckets |
| Keys, SMTP identity, Google client | Own | Own |
| GitHub environment | `staging` (one approver) | `pilot` (a second person approves) |
| Domain | `staging.<domain>` | `<domain>` |

Nothing is shared between the two except the images (same SHA) and this repository.

## 3. Provisioning (first time)
1. **Cloud account:** owner's decision (ADR-0014). Choose an Indian region and set up billing
   alarms.
2. **Managed PostgreSQL 16:** private networking only, TLS required, PITR on, deletion
   protection. Create the schema owner:
   ```sql
   CREATE ROLE vanshavali_owner LOGIN CREATEROLE PASSWORD '…';   -- as the master user
   CREATE DATABASE vanshavali OWNER vanshavali_owner;
   ```
3. **Buckets:** document bucket and backup bucket as in section 12; IAM keys scoped to each.
4. **SMTP:** verify the sender domain, publish SPF/DKIM/DMARC, request production access.
5. **VM:** Ubuntu 24.04. Run:
   ```bash
   sudo REPO_REF=main ADMIN_SSH_CIDR=<your office/VPN CIDR> deploy/pilot/scripts/bootstrap-host.sh
   ```
   It installs Docker and age, configures ufw, hardens SSH, creates the user and directories,
   generates keys and installs cron. Then **escrow the generated data keys**.
6. Fill in `/etc/vanshavali/*.env` (the `CHANGE_ME` values) and `alertmanager.yml`.
   - Generate the backup key pair **off the VM**:
     ```bash
     age-keygen -o vanshavali-backup.key   # keep the file offline; copy only the public key
     ```
   - Put the public key in `BACKUP_AGE_RECIPIENT`.
7. **DNS:** point the A record at the VM.
8. **GHCR:** as the deploy user, `docker login ghcr.io` with a read-only package token.
9. **Smoke account:** after the first deploy, register `smoke@<your domain>` through the UI and
   verify it. Put its credentials in `smoke.env`.
10. **GitHub:** create environments `staging` and `pilot` with reviewers and the four
    `DEPLOY_*` secrets.
    - Create the deploy key pair.
    - On the VM, add to `~vanshavali/.ssh/authorized_keys`:
      ```
      command="/opt/vanshavali/deploy/pilot/scripts/deploy.sh \"$SSH_ORIGINAL_COMMAND\"",restrict ssh-ed25519 AAAA… deploy@github
      ```
11. **First deploy:** Actions → Deploy → staging. Then work through the go-live checklist.

## 4. Release and rollback
`docs/operations/release-runbook.md`. In short:
1. The workflow runs the CI gate.
2. It builds images by SHA and pushes them to GHCR.
3. The protected environment is approved.
4. `deploy.sh` runs: pre-deploy DB backup → migrations (expand-only) → roll → readiness on every
   replica → smoke test.
5. On failure it starts the previous version automatically.
6. `rollback.sh` handles manual rollback. A database rollback is a separate decision.

## 5. Health checks, monitoring and logs
`docs/operations/monitoring-alerting.md`:
- metrics and what they mean;
- 18 alert rules, with unit tests for the important ones;
- an external uptime monitor;
- the log fields and what is never logged.

## 6. Restore procedure
`docs/operations/backup-restore-runbook.md`, with the drill results. A full-environment restore:
- empty DB + empty bucket → `restore.sh <backup> --identity <offline key> --objects`
  → `deploy.sh <sha>` → `smoke --verify-existing`.

Managed PITR is the first choice for database-only incidents.

## 7. Cost considerations
Orders of magnitude only. **Verify against the provider's current price sheet** before deciding;
this document does not quote prices.

| Item | Driver | Pilot expectation |
|---|---|---|
| VM | vCPU/RAM (ClamAV needs ~2 GB; OCR is CPU-bound) | One general-purpose 4 vCPU / 8–16 GB instance; staging can be smaller or stopped when idle |
| Managed PostgreSQL | Instance class + storage + PITR retention | The smallest production class; 20 GB storage covers years of a pilot (a 10k-person tree dumps to ≈ 2 MB) |
| Object storage | GB stored × versions + requests | Photos and scans are a few MB each; tens of GB at most in the pilot; versions add up to the noncurrent-expiry window |
| Backup bucket | Dumps (≈ 2–10 MB/night) × 35 days + the object mirror | Small; Object Lock has no extra storage charge beyond the retained data |
| Egress | Downloads of documents | Low for a pilot |
| Email | Per message | Negligible (verification and reset only) |
| Monitoring | Self-hosted on the VM | No extra cost; an external uptime monitor has free tiers |
| Staging | A second, smaller set of the above | Can be stopped between releases (the DB keeps its storage cost) |

The biggest lever is the VM size, the second the managed DB class. Re-certify performance before
changing either.

## 8. Scaling assumptions
- **Measured through this exact stack** (2 Oct; sandbox, shared 4 vCPU; not production capacity):
  - p95 ≤ 195 ms for single users, every operation;
  - 0% errors, with every operation's p95 under 500 ms up to 40 req/s (50 req/s on overall p95),
    on a 10k-person tree;
  - fast 503 shedding beyond that (performance.md, "Pilot stack in the sandbox").
- **Pilot load:** tens of users, single-digit req/s at peak, far below the measured capacity.
  **Certify on the staging VM** (go-live checklist) and keep peak under 70% of the certified
  rate.
- **Scale path, in order:**
  1. more `BACKEND_REPLICAS` (CPU-bound);
  2. a bigger VM;
  3. a bigger DB class;
  4. a second VM behind a load balancer (stateless API; rate limits already in Redis; move Redis
     to a managed service then);
  5. managed container hosting.

  None needs a code change. Each needs a new certification run.
- **Imports:** a GEDCOM commit runs in one request at about 15–17 ms per person (10,000 people
  take ~170 s; proxies allow 600 s). The trigger to move it to the job queue is in performance.md.
- **Workers:** one OCR job per worker replica. A burst of 50 scanned pages with 2 workers drains
  in minutes. `JobBacklog` alerts if not.
- **Storage:** grows with uploads; there is no hot path on it. Bucket storage is effectively
  unbounded.
- **Database connections:** replicas × 15 + workers × 15 must stay under `max_connections`. Use
  PgBouncer only if replicas grow past ~6.

## 9. Trusted proxies (threat T30)
- There is exactly one proxy in front of the API: Caddy, at the fixed address `172.30.0.10`.
- The backend trusts only that address (`FORWARDED_ALLOW_IPS=172.30.0.10` in compose.yml).
- Production refuses to start with `*` or a `/0` network, and logs a warning if only loopback is
  trusted. Caddy itself trusts no incoming `X-Forwarded-For`.
- **Tests:** `test_proxy_headers.py` covers uvicorn's semantics, a config guard for every shipped
  file, and pilot = Caddy's address. `test_pilot_ops.py` covers the start-up guard.
- **Sandbox edge test:** a spoofed header from the client was replaced by the real peer.

Example configurations for other topologies:

| Topology | `FORWARDED_ALLOW_IPS` | Notes |
|---|---|---|
| **Pilot (this plan)**: client → Caddy → backend | `172.30.0.10` | Docker's userland proxy must be off (bootstrap does it) so Caddy sees real client IPs |
| Local compose: client → nginx → backend | `172.28.0.10` | `docker-compose.yml` pins nginx |
| Cloud load balancer → Caddy → backend | `172.30.0.10` **and** configure Caddy `trusted_proxies static <LB CIDR>` | Caddy then appends to the LB's header. The LB's CIDR goes in Caddy, not the backend |
| Load balancer → nginx → backend (two hops) | `<nginx IP>,<LB CIDR>` | uvicorn walks the header right to left, skipping each trusted hop |
| Backend directly on the internet | (not supported) | Always put a proxy in front: TLS, limits and headers live there |

Never use `*`, or a subnet that also contains clients (e.g. a whole Docker bridge, whose gateway
is how host-published ports reach containers).

## 10. Reverse proxy and TLS
- **Certificates:** Caddy obtains them from Let's Encrypt on first start, for `VSH_DOMAIN`, and
  renews them automatically about 30 days before expiry. Certificates live in the `caddy_data`
  volume; keep it (it is not backed up, and re-issuance is automatic).
- **Prerequisites:** DNS points at the VM, and ports 80 and 443 are reachable.
- **Rate limits:** Let's Encrypt limits issuance per domain. Don't recreate the volume in a loop.
  For tests use `VSH_TLS=internal`.
- **Edge behaviour:**
  - HTTP → HTTPS with a 308;
  - HSTS (2 years, includeSubDomains);
  - HTTP/2 and HTTP/3;
  - the `Server` header is removed;
  - compression is on.
- **Body limits:** 55 MB for `/api/*` (the API's own limit is 50 MB) and 260 MB for GEDCOM
  imports (`VSH_MAX_GEDCOM_PACKAGE_BYTES` is 250 MB).
- **Timeouts:** 5 min to read a request body (large uploads on slow links), 120 s response
  header, 300 s for imports.
- **WebSockets/SSE:** not used by the application. Caddy proxies them transparently if they are
  ever added.
- **Rate-limit compatibility:**
  - the API's per-IP limits see the real client IP (section 9);
  - Caddy adds no rate limiting of its own, so there is no double counting;
  - the per-account limits are independent of IP.
- **Security headers:** the SPA's come from nginx (DAST-verified); the API's come from the app.
  Caddy adds HSTS for both.

**Sandbox verification** (2 Oct 2026; Caddy v2.10.2, local CA): redirect 308; TLS 1.3 + HTTP/2;
HSTS + CSP present and `Server` absent; spoofed `X-Forwarded-For` dropped; requests spread over 2
replicas. Upload limits:

| Upload | Size | Result |
|---|---|---|
| Document | 50 MB | 201 |
| Document | 60 MB | 413 |
| Import | 60 MB | 201 |
| Import | 250 MB | 201 |
| Import | 270 MB | 413 |

An unknown host name gets no certificate. Evidence: `docs/release/evidence/pilot-2026-10-02/`.

## 11. Database production setup
- **Roles:**
  - the master/admin user is for break-glass only, and is not on the VM;
  - `vanshavali_owner` owns the schema and runs migrations and dumps;
  - `vanshavali_app` (NOSUPERUSER, NOBYPASSRLS, not the owner) is created and kept current by
    `ensure_app_role` on every deploy.

  The API and worker use **only** `vanshavali_app`. `/health/ready` fails in production otherwise.
- **Migrations:** Alembic, run by `deploy.sh` before the new containers start. Expand-only per
  release (release runbook). Every migration has a downgrade. CI checks upgrade → `alembic check`
  → downgrade → upgrade on a clean database.
- **Connection pooling:** SQLAlchemy pool per process (5 + 10 overflow, 5 s timeout, then a 503).
  No external pooler needed at pilot scale (section 8).
- **TLS:** `sslmode=verify-full` with the provider's CA bundle in the URL (env-variables doc).
- **Backups:** managed automated backups + PITR (7+ days), plus nightly encrypted dumps
  (backup.sh, 20:41 UTC = 02:11 IST).
- **Monitoring:** `vsh_db_up` + the pool gauges from the app; the provider's CPU, storage,
  connection and replication metrics as provider alarms.
- **Maintenance:**
  - minor-version upgrades in the provider's maintenance window (announced to the pilot);
  - major upgrades (PostgreSQL 17+) rehearsed on staging first, from a restored copy;
  - `ANALYZE`/autovacuum are left on (defaults);
  - daily `purge-deleted-documents` and a weekly orphan report run from cron.

## 12. Object storage production setup
Applies to every document class: photos, birth certificates, property records, Kundli, GEDCOM
uploads and packages, archives. All of them live in **one private bucket** under app-chosen keys.
Every object is AES-256-GCM encrypted by the app (STANDARD or VAULT key, ADR-0004) **before** it
reaches the bucket.

| Requirement | Setting |
|---|---|
| Private by default, no public listing | Block Public Access (all four) on; no bucket policy with `Principal: *`; no ACL grants; no static website |
| Signed URLs only | Downloads go through the API's signed, user-bound, 5-minute links (`/api/v1/files/{token}`). The bucket is never exposed, and no presigned S3 URLs are issued |
| Encryption at rest | App-level AES-GCM (keys never in the bucket's account) **plus** default bucket encryption (SSE-S3 or SSE-KMS) |
| TLS in transit | Bucket policy denying `aws:SecureTransport = false` |
| Versioning and backup | Versioning on, so overwrites and deletes are recoverable; the nightly `mirror-to-backup` copies new objects into the backup bucket (separate account) |
| Lifecycle and retention | Expire noncurrent versions after 30 days. Soft-deleted documents are purged after `VSH_DOCUMENT_PURGE_AFTER_DAYS` (30) by the daily job, which removes every version. Object-lock retention (if any) must be shorter |
| Malware scanning | Every upload is scanned by clamd **before** it is processed or served; results `pending` → `clean`/`infected`; infected files are never served or previewed; the scanner down means uploads wait, never pass |
| Least privilege | The app's IAM key: `s3:GetObject`, `PutObject`, `DeleteObject`, `ListBucket`, `ListBucketVersions`, `DeleteObjectVersion` on this bucket only |
| Backup bucket | Separate account or at least a separate key; Object Lock (governance, 35 days); its key can put/get/list but not delete; lifecycle 35 days |
| Monitoring | `StorageErrors` alert (app side); the provider's 4xx/5xx metrics and access logs (for incident forensics) |

**Storage operations:**
- **Restore a deleted object:** by version ID (provider console, or `aws s3api get-object
  --version-id`).
- **Bucket lost:** `ops_backup mirror-from-backup`.
- **Orphan report:** weekly, from cron. Deleting orphans needs review (`sweep-orphans --delete`).
- **Never change the data keys without the re-encryption tool** (secrets-management.md).

## 13. Smoke test
`python -m app.cli.smoke` (stdlib only; runs from the image). Synthetic data, a dedicated
account, and the smoke tree deleted afterwards. It covers:
1. health and readiness (RLS enforced);
2. SPA and CSP;
3. login;
4. create a tree;
5. add people + a link;
6. family/descendants load;
7. photo upload (scanned clean);
8. GEDZIP upload;
9. import report + commit (photo matched);
10. create a property;
11. property document (scanned clean);
12. logout/login;
13. persistence + checksummed downloads.

`--verify-existing` checks a restored tree read-only, plus the GEDCOM export and the audit trail.
Run automatically by deploy.sh and rollback.sh. Sandbox result: 13/13 in about 2.5 s through
Caddy, TLS and ClamAV.

## 14. Support during the pilot
- **Owner:** the support contact. Pilot users report problems with the time and, if shown, the
  error's request ID.
- **Outages:** announced in the pilot group (release runbook).
- **Incidents:** `docs/operations/incident-response.md`.
