# ADR-0014: Pilot hosting — one VM running Docker Compose, managed PostgreSQL and S3, in India

- Status: Accepted (topology) · Provider account: **to be confirmed by the owner** · Date: 2026-10-02
- Relates to: ADR-0001 (modular monolith), ADR-0002 (PostgreSQL, RLS), ADR-0004 (document storage),
  ADR-0005 (sessions, email), open question Q12 (hosting region, RPO/RTO)
- Supersedes: the "Production target (ASSUMPTION)" in `implementation-plan.md` §12 for the pilot

## Context
The application is production-pilot ready (`docs/release/production-readiness.md`, 1 Oct 2026).
Hosting was the last undecided item. What the pilot must carry:

- **Processes:** one API (FastAPI/uvicorn), one background worker (RQ: scanning, previews, OCR, email),
  nginx serving the SPA, Redis (queue, rate limits), clamd (malware scanning, ~1.5–2.5 GB RAM for
  signatures), PostgreSQL 16 with row-level security, and S3-compatible object storage.
- **Load:** a controlled pilot of a few families. The sandbox certification measured p95 ≤ 101 ms
  for single users and up to 50 req/s sustained on 4 shared vCPUs (performance.md). A pilot needs
  a small fraction of that.
- **Data:** living people, birth certificates and property papers. The DPDP Act 2023 and open
  question Q12 assume **India-resident data** (an Indian region).
- **Team:** no dedicated operations staff. Every component we run ourselves is a component someone
  must patch, back up and restore.
- **Hard requirements from earlier ADRs:**
  - point-in-time recovery for the database (backup-restore.md);
  - a private, versioned bucket (ADR-0004);
  - TLS everywhere;
  - the app connecting as a non-owner role (ADR-0002 §7);
  - trusted-proxy addresses known exactly (threat T30).

## Options considered

| | A. One VM, everything self-hosted (Compose incl. PostgreSQL + MinIO) | B. Managed application platform (PaaS) | **C. One VM for the stateless services + managed PostgreSQL + managed S3** |
|---|---|---|---|
| Simplicity | Simplest to stand up; one box | Simple deploys, but clamd, tesseract, a worker and private networking each need platform-specific workarounds | One `docker compose` on one VM; two managed services configured once |
| Security | We patch the DB and object store ourselves; disk-level encryption is ours to set up | Strong defaults; proxy chain and client-IP rules are platform-specific (T30 must be re-derived) | Provider patches DB and storage; private bucket, SSE and TLS-only are settings; the proxy chain is ours and explicit |
| Cost (order of magnitude, verify against current price sheets) | lowest: one VM | highest: per-service pricing, plus a managed Redis and DB anyway | one VM + the smallest managed PostgreSQL with PITR + storage by the GB |
| Operational burden | **High**: WAL archiving, PITR, PostgreSQL upgrades, MinIO durability and backups all ours. MinIO's community distribution also changed in 2025 (prebuilt images are no longer a dependable supply line) | Lowest day to day; highest when something platform-specific breaks | Low: backups, PITR, minor-version patching and storage durability are the provider's; we own the VM and the containers |
| Backups and restore | Must build and drill PITR ourselves | Provider-specific | Managed PITR (minutes RPO) **plus** our encrypted nightly `pg_dump` to a separate bucket (`deploy/pilot/scripts/backup.sh`) |
| Reliability | One disk holds everything: a VM loss is a restore from off-site backups | Good | A VM loss loses no data (it holds only Redis' queue); rebuild the VM from this repository and redeploy |
| Data in India | Any provider with an Indian region | Few PaaS platforms offer an Indian region | Major clouds offer VM + managed PostgreSQL + S3 in Mumbai/Hyderabad (e.g. AWS ap-south-1) |
| Scaling later | Hard: the database shares the VM | Easy | API replicas on the VM first (`BACKEND_REPLICAS`), then a second VM behind a load balancer; DB and storage scale independently |

## Decision
**Option C.**
- **Compute:** one Linux VM (Ubuntu 24.04 LTS, 4 vCPU / 8–16 GB RAM) in an Indian region runs the
  stateless services with Docker Compose (`deploy/pilot/compose.yml`):
  - Caddy (TLS and HTTP→HTTPS);
  - the nginx SPA image;
  - `backend` (N single-process replicas);
  - `worker`;
  - Redis (AOF on a volume);
  - clamd;
  - optional Prometheus, Alertmanager and node-exporter.
- **Database:** PostgreSQL 16, managed, in the same region, with PITR, TLS required and no public
  endpoint.
- **Object storage:** private S3, same region:
  - Block Public Access;
  - versioning;
  - default encryption;
  - lifecycle rules.

  On top of the app's own AES-256-GCM encryption (ADR-0004).
- **Backups:** a **second bucket** holds the encrypted nightly dumps. It uses separate, write-only
  credentials.
- **Email:** transactional email from a provider that supports STARTTLS on port 587, with SPF, DKIM
  and DMARC on the sender domain.
- **Reference implementation:** **AWS ap-south-1 (Mumbai)**, i.e. EC2, RDS for PostgreSQL 16, S3 and
  SES. It is chosen because every requirement above is a documented feature there:
  - PITR;
  - S3 Object Lock and versioning;
  - SSE-KMS;
  - SES in the same region.

  It also matches the code's default `s3_region`. Any provider offering the same five primitives
  in India is equivalent: nothing in the repository is AWS-specific beyond S3-compatible APIs.
  **The owner confirms the provider and account** (a billing decision, not an architectural one).
- **Edge:** Caddy terminates TLS (automatic ACME certificates and renewal) and is the **only**
  published service (ports 80/443).
  - It proxies `/api/*` straight to the backend replicas, re-resolving them every few seconds.
  - Everything else goes to the nginx SPA container.
  - Caddy has a fixed address on the Compose network, and that address is the entire
    `FORWARDED_ALLOW_IPS` (T30).
- **Releases:** CI builds the images once, tagged with the commit SHA, and pushes them to GHCR.
  - A GitHub Actions `deploy` workflow can run only after the full CI gate passes on `main`.
  - It needs approval of a protected `pilot` environment.
  - It then runs `deploy/pilot/scripts/deploy.sh <sha>` over SSH, as a deploy user restricted to
    that command.
  - The script takes a backup first, then migrates, rolls the containers and smoke-tests.
- **Environments:** `staging` and `pilot` are separate stacks. Each has its own VM, database
  instance, buckets, keys, SMTP identity, Google OAuth client and GitHub environment. Staging never
  holds real family data.

## Consequences
- **Single point of failure:** the VM. A host failure is an outage (RTO = rebuild + redeploy,
  measured in the restore drill) **but not a data loss**: the canonical data live in the managed
  DB and S3. That is acceptable for a controlled pilot. The next step is a second VM behind a
  load balancer, and nothing in the design prevents it (stateless API, Redis-backed rate limits).
- **Redis on the VM:**
  - Losing it loses queued jobs and the rate-limit counters, never canonical data.
  - Documents left `pending` can be re-queued.
  - AOF persistence makes a restart lossless.
- **Two database roles and two secret files:** the migrate step uses the owner credentials,
  while backend and worker use the RLS-bound app role. They live in separate files on the host
  (`docs/security/secrets-management.md`).
- **Deploys briefly interrupt service** (containers are recreated, so allow a few seconds of 502s
  per release). Pilot releases happen in an announced window. Blue/green is deferred until there
  is a second VM.
- **Metrics are per process.**
  - Each backend replica runs one uvicorn process, so Prometheus scrapes every replica through
    Compose DNS.
  - Before this ADR, `--workers N` behind one port meant a scrape saw one random worker.
  - Worker-side counters (email, OCR, imports) go through Redis (`app/core/events.py`).
- **No Kubernetes, no service mesh, no multi-region.** The triggers in `implementation-plan.md` §12
  still apply.

## Stress test
- *"What if the managed DB provider is unavailable?"* Restore the latest encrypted dump into any
  PostgreSQL 16 (backup-restore runbook, drilled). Point `VSH_DATABASE_URL` at it, and RPO becomes
  the dump age (≤ 24 h).
- *"What if the VM is compromised?"* It holds the data keys and the DB app-role password, but not
  the DB owner password beyond deploy time, and not the backup bucket's read credentials. Rotate
  per `secrets-management.md`. The backups stay out of reach (write-only key; Object Lock on the
  backup bucket).
- *"Can the pilot outgrow one VM?"* The sandbox handled 50 req/s on 4 shared vCPUs. A pilot with
  tens of families is orders of magnitude below that. Re-certify on the staging VM before inviting
  more users (go-live checklist).
- *"Why Caddy and not nginx with certbot?"* It is one component instead of two (TLS issuance and
  renewal are built in, with no cron and no reload hooks), and it can re-resolve the backend
  replicas. nginx stays as the SPA server, where its headers and caching are already tested by DAST.
