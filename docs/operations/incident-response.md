# Pilot incident response

For the pilot topology (ADR-0014). Commands assume the VM, as the deploy user:
```bash
cd /opt/vanshavali && source deploy/pilot/scripts/lib.sh   # gives `dc` (docker compose for the stack)
```

## For every incident
1. **Acknowledge:** the alert email, or the user report. One person is the **incident lead**
   (default: the owner).
2. **Assess the impact:**
   - Is data at risk (loss, corruption, exposure), or only availability?
   - Is any **personal data exposed**? If yes, also follow "Personal-data breach" below.
3. **Stabilise first, diagnose second.** Roll back a recent release (`rollback.sh`) before
   debugging it.
4. **Communicate:** if pilot users are affected for more than 5 minutes, post one message in the
   pilot group, then a follow-up when resolved (release-runbook.md, "Incident communication").
5. **Record:** an entry in the incident log, with:
   - timeline (UTC);
   - detection (alert or user);
   - impact;
   - root cause;
   - fix;
   - follow-ups (each with an owner);
   - for anything touching security, the threat-model row added or updated.

**Useful evidence** (never paste secrets or family data into tickets or chat):
```bash
dc ps; dc logs --since 1h --tail 500 backend worker | grep -E '"level": "(ERROR|WARNING)"'
dc exec -T backend python -c "import urllib.request as u; print(u.urlopen('http://127.0.0.1:8000/api/v1/health/ready').read())"
curl -s -H "Authorization: Bearer $(cat /etc/vanshavali/metrics_token)" ... # or Prometheus at localhost:9090
```
Every API error response carries `X-Request-ID`. Ask the user for it (or the time), then run
`dc logs backend | grep <id>`.

## Scenarios

### Service outage (site unreachable or 5xx everywhere)
1. Is it the VM?
   - The external uptime monitor fails, and SSH fails: check the provider console (instance
     state, CPU credits, disk). Reboot from the console.
   - The stack has `restart: unless-stopped`, so it comes back by itself.
2. Containers: `dc ps`. Restart any that are not running or unhealthy (`dc up -d`). Caddy down
   means nothing answers on 443.
3. A release just happened? Run `rollback.sh`.
4. Readiness failing? It names the dependency (database, redis, rls). Go to that scenario below.
5. **VM lost entirely:**
   1. Create a new VM and run `bootstrap-host.sh`.
   2. Restore `/etc/vanshavali` from the escrow/password manager.
   3. Point DNS at the new address.
   4. `deploy.sh <current sha>`.

   No data lives on the VM except Redis' queue (ADR-0014). RTO is measured in the restore drill.

### Database failure (`DatabaseUnavailable`)
1. Check the provider's console: instance status, storage full, max connections, maintenance
   window.
2. **Connections exhausted:** look for a runaway process. `dc restart backend` releases the pool.
   Check that replicas × (pool + overflow) is under `max_connections`.
3. **Storage full:** grow the storage (managed instances usually grow online).
4. **Instance unrecoverable or data corrupted:** restore with managed **PITR** into a new
   instance, to just before the incident.
   - Update `VSH_DATABASE_URL` in app.env and migrate.env, then `deploy.sh <current sha>` with
     `SKIP_BACKUP=1`.
   - If PITR itself is unavailable (provider or account loss), restore the latest encrypted dump
     instead (`backup-restore-runbook.md`). RPO then becomes the dump age (≤ 24 h).
5. Afterwards, check `ensure_app_role` ran (deploy.sh does it) and readiness reports
   `rls: enforced`.

### Redis failure (`JobQueueUnreachable`)
- **Impact:**
  - uploads stay "pending scan";
  - emails are not sent;
  - rate limits fail closed or open, depending on the limiter;
  - readiness fails, so the API is pulled from service.
- **Fix:**
  - `dc logs redis`, then `dc up -d redis`. AOF persistence restores queued jobs.
  - If the AOF is corrupt:
    1. Move the volume aside: `docker volume create` a fresh one, edit nothing else.
    2. Start Redis empty.
    3. Re-queue stuck documents. They remain `pending` and the document list shows them; the
       "reprocess" action re-queues them.
    4. Users re-request verification and reset emails.

### Object-storage failure (`StorageErrors`, uploads/downloads fail with 503 `storage_unavailable`)
1. Check the provider's status page and the bucket in the console.
2. **Credentials:** were the S3 keys rotated or revoked? Test them:
   ```bash
   dc --profile tools run --rm tools python -c "from app.core.storage import get_store; print(get_store().exists('probe'))"
   ```
3. **Bucket policy** changed, or Block Public Access interference? Compare with the
   pilot-deployment-plan's bucket policy.
4. **Objects deleted:** versioning keeps previous versions. Restore them by version ID.
   - If the bucket itself was lost, restore from the backup bucket's `objects/` mirror:
     `ops_backup mirror-from-backup` (backup-restore runbook).
5. While storage is down, the app keeps working for everything except files. No data is lost:
   uploads fail cleanly, and users retry.

### SMTP outage (`EmailDeliveryFailing`)
Follow `email-runbook.md`, "Common failures" and "Recovery after an outage". Registration and
password reset are blocked; nothing else is.

### Suspected account compromise (a user reports it, or the audit log shows unexpected changes)
1. **Contain:** as the tree owner (or the user), revoke the user's sessions ("Sign out other
   devices", or close the account).
   - If an attacker changed the password, use the password-reset flow.
   - An admin can force a password change: `must_change_password`.
2. Check the audit log (`/trees/{id}/audit`) for what the account did. `audit_event` is
   append-only, so the record is reliable. IP addresses and browsers are kept for one year only
   (ADR-0033); older entries still show who did what and when. Revert changes from the audit trail and person history.
3. If the account was a tree owner or admin, review grants and invitations it created. Revoke
   unknown ones, and revoke pending claim links for affected people.
4. If credential stuffing is suspected (many accounts):
   - Check the login 429 rates and `rate_limited` errors per IP in the logs.
   - Lower `VSH_LOGIN_RATE_LIMIT_PER_MINUTE` temporarily.
   - Confirm the client IPs are real, not Caddy's (threat T30).
5. If personal data was seen by the attacker, this is a breach (below).

### Leaked document URL
- **Design:** download links are signed, bound to the user who requested them, and expire in
  5 minutes (`VSH_DOWNLOAD_URL_TTL_SECONDS`, threat T5). A leaked link is useless to others and
  soon dead.
- If you suspect the signing key itself leaked:
  1. **Rotate `VSH_SIGNING_KEY`** (secrets-management.md). All outstanding links die at once.
  2. Restart the backend.
  3. Review the logs: `/api/v1/files/{token}` route hits around the time.
- **Bucket objects** are not public and are encrypted by the app. A raw bucket URL leaks nothing
  without the data keys.

### Compromised OAuth (Google) client secret
1. In Google Cloud Console, open Credentials → the client. Add a new secret, put it in app.env,
   run `dc up -d backend`, then **delete the old secret**.
2. Check the redirect URIs registered for the client. Remove anything not
   `https://<domain>/api/v1/auth/google/callback`.
3. Review recent `auth.google_*` audit events for unexpected account links. Unlink suspicious
   ones and reset those accounts' passwords.
4. The secret alone cannot sign anyone in (state + PKCE + ID-token checks, threat T26). Still
   treat it as compromised.

### Malware upload (scanner reported `infected`, or a user reports a malicious file)
1. **The pipeline already stops it:** infected files are never served or previewed, and stay
   quarantined (ADR-0004).
2. Identify the uploader from `document.created_by` and the audit log. If it was deliberate,
   suspend the account and remove it from trees.
3. If a malicious file got through as `clean` (scanner miss):
   1. Soft-delete the document.
   2. Run purge for it after review.
   3. Check whether anyone downloaded it (audit log, `/files` route hits).
   4. Update ClamAV signatures (`dc restart clamav`; the image refreshes them).
   5. Report the sample hash to ClamAV.
4. If the **scanner is down**: uploads stay `pending`, never served unscanned (fail closed).
   Restart `clamav`.

### Failed restore (during an incident or a drill)
- **`sha256sum -c` fails:** the artefact is damaged. Use the previous night's backup, and check
  the backup bucket's versions.
- **`age -d` fails:** wrong identity file. The identity is the **offline** key from the escrow.
  Old dumps may need the previous identity, which is kept (secrets-management.md).
- **`pg_restore` fails:**
  - Is the target empty and PostgreSQL 16? Are the `pg_trgm` and `unaccent` extensions available?
  - Retry into a fresh database. Never restore over a live database.
- **`check-restore` reports count mismatches outside the manifest's range:** do not put the
  restore into service. Restore an older backup, or use PITR.
- **Documents fail to download after restore** (500, or checksum mismatch): the data keys don't
  match the source. Use the **escrowed** keys of the environment the backup came from.
- **Last resort:** managed PITR is independent of these dumps (and vice versa). Try the other path.
  Escalate to the provider's support with the instance ID.

### High error rate (`HighServerErrorRate`)
1. A deploy in the last hour? Run `rollback.sh` first.
2. Group the errors by route and code:
   ```bash
   dc logs --since 15m backend | grep '"status": 5' | grep -o '"route": "[^"]*"' | sort | uniq -c
   ```
3. Read the code: `server_busy` is capacity, so add a replica (`BACKEND_REPLICAS`, then
   `dc up -d`). `storage_unavailable` is storage. Plain 500s are a bug: capture the `request_id`
   and the exception from the logs, then fix with a regression test.
4. If the cause is a DB slowdown, check the provider's performance insights for a slow query.
   The statement timeout (15 s) bounds it.

## Personal-data breach (any scenario where family data may have been exposed)
The platform is a Data Fiduciary under the DPDP Act 2023.
1. **Contain:** revoke the access path (credentials, sessions, keys). Preserve the evidence: logs,
   audit events, provider access logs.
2. **Assess:** whose data, what fields, living or deceased, minors, which documents. Classify
   VAULT documents (certificates, property papers) as high impact.
3. **Notify:**
   - the Data Protection Board and the affected data principals, in the form and time the DPDP
     Rules require (**get legal advice immediately**; open question Q13);
   - the tree owners concerned.
4. **Remediate and record:** root cause, fix with a regression test, threat-model update.
