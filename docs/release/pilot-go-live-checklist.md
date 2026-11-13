# Pilot go-live checklist

Tick an item only when it is done **and** its evidence is recorded:
- a link;
- a measured result in `docs/release/production-readiness.md`;
- or a name and date.

"Done in the sandbox" is evidence for the repository, not for the pilot environment.

- **Blocking:** must be complete before the first invited family signs in.
- **Required before public launch:** may stay open during a controlled, invite-only pilot.
- **Recommended:** operational improvements; schedule them.

Status as of 2 Oct 2026: items marked *(prepared)* have everything they need in the repository
(scripts, runbooks, tests), but have not been executed against real infrastructure.

## Blocking (before the pilot)

### Hosting and DNS
- [ ] Owner confirms the provider and account for ADR-0014 (reference: AWS ap-south-1), with
  billing alerts set.
- [ ] VM (Ubuntu 24.04, 4 vCPU / 8–16 GB) created in an Indian region;
  `deploy/pilot/scripts/bootstrap-host.sh` run. *(prepared; not run on a real VM)*
- [ ] Staging environment created the same way, separate from the pilot (own VM, DB, buckets,
  keys, Google client, SMTP identity).
- [ ] DNS: `A` records for the pilot and staging names. Publish no `AAAA` unless Docker IPv6 is
  configured (client IPs, threat T30). TTL 300 during the pilot.

### TLS and edge
- [ ] Caddy obtained real certificates for both names (`dc logs caddy | grep "certificate obtained"`).
  *(edge config verified in the sandbox with a local CA: redirect, HSTS, CSP, upload limits,
  client IP)*
- [ ] `curl -I http://<domain>` returns 308 to https, and `https://<domain>` returns 200 with HSTS.
  An SSL Labs or `testssl.sh` grade of A is recorded.

### Database
- [ ] Managed PostgreSQL 16 in the same region:
  - no public endpoint;
  - TLS required;
  - PITR enabled (7+ days);
  - automated backups;
  - deletion protection;
  - `pg_trgm` and `unaccent` available.
- [ ] A schema-owner role (not the master user) owns database `vanshavali`. Its URL is in
  migrate.env. The master password lives only in the password manager.
- [ ] First deploy ran migrations and `ensure_app_role`. `/health/ready` reports
  `"rls": "enforced"`, which means the app connects as `vanshavali_app` (NOSUPERUSER,
  NOBYPASSRLS, not the owner).
- [ ] `max_connections` ≥ replicas × 15 + workers × 15 + 20 headroom.

### Redis
- [ ] The Redis container runs with AOF (compose.yml). `vsh_queue_up == 1`.

### Object storage
- [ ] Document bucket, configured as follows:
  - private (Block Public Access on), no bucket policy granting public read, no website hosting,
    no public listing;
  - versioning on;
  - default encryption (SSE-S3 or SSE-KMS);
  - TLS-only bucket policy (`aws:SecureTransport`);
  - lifecycle rule expiring noncurrent versions after 30 days. Keep any object-lock retention
    shorter than `VSH_DOCUMENT_PURGE_AFTER_DAYS` (ADR-0004).
- [ ] Backup bucket configured as follows:
  - separate (ideally a separate account);
  - Object Lock (governance, 35 days);
  - write/read-only credentials (no delete);
  - lifecycle expiring backups after 35 days.
- [ ] IAM: the app's key can only reach the document bucket; the backup key only the backup
  bucket.

### Email
- [ ] SMTP provider account out of any sandbox; sender domain verified.
- [ ] SPF, DKIM and DMARC published for the sender domain. A test message shows `spf=pass`,
  `dkim=pass` and `dmarc=pass`.
- [ ] `mail_check --send-to` passes on the pilot VM (email-runbook.md).
- [ ] End to end: registration → verification email → link works; password reset works. Check
  both English and Hindi. *(proven in the sandbox drill against a STARTTLS sink)*

### Secrets
- [ ] Every `CHANGE_ME` in `/etc/vanshavali/*.env` and `alertmanager.yml` replaced. Files are
  mode 600 (deploy.sh refuses otherwise).
- [ ] **Data keys and the backup age identity escrowed** offline, with two people knowing where
  (secrets-management.md).
- [ ] The age identity is **not** on the VM.
- [ ] The VM's start-up guards pass: production refuses dev keys, `*` proxy trust, non-SMTP mail,
  http URLs, weak keys and `@localhost` senders.

### Google sign-in (if enabled for the pilot)
- [ ] A separate OAuth client for the pilot (and one for staging), type "Web application".
- [ ] Redirect URI `https://<domain>/api/v1/auth/google/callback` exactly.
- [ ] Consent screen published, with app name, support email and privacy policy URL.
- [ ] Sign in, link and unlink tested on the pilot. Otherwise leave the client ID empty; the
  button is then hidden.

### Trusted proxies
- [ ] `FORWARDED_ALLOW_IPS` is the Caddy address only (compose.yml; `test_proxy_headers.py`
  guards it).
- [ ] On the pilot, the session list (`/settings` → sessions) shows your **real public IP**, not
  `172.30.0.x`. This proves Docker's userland proxy is off and client IPs survive (threat T30).

### Platform administrators (ADR-0028)
- [ ] `VSH_MASTERDATA_CONSOLE_ENABLED` stays `false` (the default) until two named administrators
  hold `master_data.admin`, each granted with `app.cli.platform grant` and each signed in once with
  password + authenticator code (`docs/operations/platform-admins.md`). Record both names and dates.
- [ ] No role or shared mailbox holds a capability (`app.cli.platform list --all`).

### Migrations and release process
- [ ] GitHub environments `staging` and `pilot` created:
  - required reviewers;
  - pilot: prevent self-review;
  - environment secrets `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`.
- [ ] The deploy key's `authorized_keys` line has the forced command (deploy.sh) and `restrict`.
- [ ] First `Deploy` workflow run to staging green (gate → images → approval → deploy with smoke).
- [ ] The same SHA deployed to the pilot. Its smoke test is green.

### Backups and restore
- [ ] Nightly backup cron ran at least once on the pilot VM:
  - `vsh_backup_last_status 1`;
  - the dump is in the backup bucket;
  - the heartbeat is received.

  *(backup.sh proven in the sandbox drill)*
- [ ] **Restore drill on production-like infrastructure:**
  1. Restore the pilot's latest dump into a **new** managed instance and a new bucket, with
     staging keys replaced by the pilot's escrowed keys, in an isolated environment.
  2. Run `smoke --verify-existing`.
  3. Record RTO and RPO in production-readiness.md.
  4. Destroy the restored copy afterwards (it holds real data).

  *(sandbox drill results: backup-restore-runbook.md)*
- [ ] Managed PITR tested once: restore to a point in time into a new instance, and check row
  counts.
- [ ] RPO/RTO targets agreed by the owner (proposal: RPO ≤ 15 min via PITR, ≤ 24 h via dumps;
  RTO ≤ 4 h).

### Monitoring and alerting
- [ ] `--profile monitoring` running. All Prometheus targets are up (each backend replica, node).
- [ ] `alertmanager.yml` filled in. A test alert reached the operations mailbox
  (monitoring-alerting.md).
- [ ] An external uptime monitor on `https://<domain>/api/v1/health` (1-minute interval, alerts
  by email or SMS).
- [ ] Provider alarms: DB CPU, free storage, connections; bucket 4xx/5xx; billing.

### Performance
- [ ] Certification re-run **on the staging VM** with the generator on a separate machine
  (performance.md runbook). Results recorded: pilot capacity in req/s at p95 < 500 ms. The pilot
  size must stay below 70% of it. *(sandbox certification exists; pilot hardware not certified)*

### Accessibility and language (for the pilot audience)
- [ ] Manual screen-reader pass:
  - at least NVDA + Firefox and TalkBack + Chrome, for scenarios A, C and G;
  - results recorded in `docs/accessibility/manual-test-checklist.md` §4.

  **No result exists yet.**
- [ ] Native-Hindi language review of priorities 1–4 (consent, privacy, registration, email),
  signed off in `docs/localization/hindi-review-checklist.md`.

### Landing-page visitor estimate (ADR-0032)
- [ ] `VSH_VISITOR_STATS_ENABLED` stays `false` (the default) unless **all** of these hold:
  - a public English and Hindi privacy notice describes the `vsh_impact_visitor` cookie;
  - counsel has answered Q20;
  - the owner has approved ADR-0032 (done: accepted 13 Nov 2026);
  - `VSH_RATE_LIMIT_BACKEND=redis`.

  Record the activation date and a review date 90 days later.
- [ ] No `VITE_DONATION_LINK_*` is set until the hosted checkouts, receipts and refunds have been
  reviewed (`docs/architecture/landing-impact-and-support.md`).

### Legal (pilot scope)
- [ ] The public privacy notice (`/privacy`, English and Hindi) reviewed by counsel and approved by
  the owner. `VITE_PRIVACY_CONTACT_EMAIL` is set to a monitored mailbox in the frontend build.
- [ ] Privacy notice and terms for the pilot participants, approved by the owner. Each invited
  family is told it is a pilot.
- [ ] If the pilot includes families outside the owner's circle: legal review of the consent and
  attestation wording (open question Q13) **before** they are invited.

### Rollback plan
- [ ] `rollback.sh` exercised on staging: deploy A → deploy B → roll back to A with the smoke test
  green.
- [ ] Pilot users know the support contact and how outages are announced.

## Required before public launch
- [ ] **Independent penetration test** completed (scope: `docs/security/pentest-scope.md`).
  Every high and critical finding fixed and retested.
- [ ] **Legal review** (DPDP Act 2023):
  - consent and attestation statements;
  - privacy notice;
  - claim and erasure flows;
  - breach notification procedure;
  - lawful basis for unclaimed living relatives (Q13).

  Approved Hindi and English texts are versioned in `statements.py`.
- [ ] Native-Hindi review of every priority group (1–8), signed off.
- [ ] Full manual assistive-technology pass (the whole matrix: NVDA, JAWS, VoiceOver
  macOS/iOS, TalkBack).
- [ ] Capacity re-certified for the expected public load, plus an HA decision (second VM behind a
  load balancer, or managed compute).
- [ ] `SECURITY.md` and a published security contact.
- [ ] DAST workflow run on GitHub against staging, with the results reviewed (the weekly schedule
  is in `dast.yml`).
- [ ] Data-key rotation tool (re-encrypt objects under new keys). Today data keys cannot be
  rotated in place (secrets-management.md).

## Recommended (operational improvements)
- [ ] Ship logs to a managed log service (same exclusions; 30–90 day retention).
- [ ] TLS-expiry probe (blackbox exporter) and dashboards (Grafana) on top of Prometheus.
- [ ] OpenTelemetry tracing (deferred since Phase 8).
- [ ] Quarterly restore drill and secret rotation on the calendar.
- [ ] Separate SMS/chat paging for `page` alerts once there is an on-call rota.
- [ ] Image signing (cosign) and SBOMs for the GHCR images.
- [ ] Weekly automatic `apt` security updates verified (unattended-upgrades is enabled by
  bootstrap).
- [ ] People-list index when any tree approaches 100k people (performance.md trigger).

## Heritage visualization milestone (before enabling the features on the pilot)
- [ ] The `reminders` scheduler service is running (`docker compose ps reminders`) and a test
      reminder ("Send me a test" on the Reminders page) arrives by email.
- [ ] SMS / WhatsApp stay `disabled` unless a provider is configured end to end
      (`docs/operations/notification-providers.md`: credentials in the secret manager, DLT
      registration for SMS, approved WhatsApp template, a verified test number).
- [ ] **Remotion licence** checked for the operating organisation (free only for individuals,
      non-profits and companies of up to 3 people); otherwise keep `VSH_RENDER_BACKEND=disabled`.
- [ ] If renders are enabled: render-worker image built and deployed (`--profile render`), 2 CPUs /
      3 GB, Noto fonts present (Hindi names render correctly in a test export), one poster and one
      MP4 produced on the pilot.
- [ ] Retention for render artifacts and delivery history agreed (deferred in code).

