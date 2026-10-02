# Release runbook (staging and pilot)

Applies to the pilot topology (ADR-0014): one VM running `deploy/pilot/compose.yml`, managed
PostgreSQL and S3.
- **Releases are commits on `main`**, deployed by image tag (the commit SHA).
- **Staging first, always.** The same tag goes to the pilot only after staging passed its smoke
  test.

## Normal path: the GitHub `Deploy` workflow
1. **Merge to `main`.** The pull request passed CI: backend, frontend, e2e, security, docker,
   deploy-config.
2. **Staging.**
   - In GitHub, go to **Actions → Deploy → Run workflow** and choose `staging`.
   - The workflow re-runs the **full CI gate on this exact commit**, then builds and pushes the
     images (`ghcr.io/<owner>/vanshavali-{backend,frontend}:<sha>`).
   - It then waits for approval of the `staging` environment.
3. **Approve.** A reviewer approves the environment. The `deploy` job SSHes to the VM, whose
   forced command runs `deploy/pilot/scripts/deploy.sh <sha>`. The steps are listed below.
4. **Check staging:**
   - the smoke test in the job log;
   - the Prometheus targets are up;
   - a quick manual look in the browser (English and Hindi).
5. **Pilot:** run the workflow again with `pilot`. It rebuilds nothing new: the same SHA, same
   images. A second person approves, then deploy.sh runs on the pilot VM.
6. **Watch for 30 minutes** (see "Monitoring after a release").

**Gate rules:**
- The workflow refuses any ref other than `main`, so feature branches cannot be deployed.
- A failing gate stops before images are built.
- Environments `staging` and `pilot` are protected:
  - required reviewers;
  - pilot: a reviewer other than the person who triggered the run;
  - the secrets live only in the environment.

Configure this once in **Settings → Environments** (go-live checklist).

## What `deploy.sh <sha>` does (also the manual path)
On the VM, as the deploy user: `/opt/vanshavali/deploy/pilot/scripts/deploy.sh <sha>`
1. **Preflight:** config files exist with mode 600, the Compose file renders, and the images for
   `<sha>` are pulled.
2. **Database backup** (pre-deploy): `backup.sh pre-<sha> --db-only`.
   - An encrypted `pg_dump` plus manifest goes to the backup bucket.
   - This is the fallback if a migration must be undone.
   - It is skipped on the very first deploy.
3. **Migrations:** `migrate` runs `alembic upgrade head` as the schema owner, then
   `ensure_app_role`, which keeps the RLS-bound app role's grants current.
4. **Roll:** backend, worker and frontend containers are recreated on the new images. Caddy, Redis
   and ClamAV are kept.
   - **Expect a few seconds of errors** while containers restart (there is a single VM; see
     ADR-0014).
   - Announce pilot releases in the pilot group chat; prefer quiet hours.
5. **Readiness:** every backend replica must answer `/health/ready` (DB, Redis, RLS in force)
   within 4 minutes.
6. **Smoke test** through Caddy with the dedicated smoke account (`app.cli.smoke`, 13 steps):
   - health;
   - SPA and CSP;
   - login;
   - tree;
   - people;
   - chart;
   - photo upload and scan;
   - GEDZIP import, report and commit;
   - property;
   - property document;
   - logout/login;
   - persistence and checksummed downloads;
   - then the smoke tree is deleted.
7. **Record:** `/var/lib/vanshavali/release/{current,previous,history}`.

**On failure:**
- If step 4, 5 or 6 fails, deploy.sh **automatically starts the previous version again**. The
  database is not changed back.
- It exits non-zero and the workflow run fails.
- `NO_AUTO_ROLLBACK=1` leaves the failed version running for diagnosis (staging only).

### Worker and frontend
They deploy with the backend, from the same tag, in step 4.
- **Worker:** the worker gets `stop_grace_period: 120s`, so a running OCR job can finish.
- **Queued jobs:** jobs still queued are picked up by the new worker. Job function names are
  stable across releases; if a release renames a job function, drain the queue first (wait for
  `vsh_jobs_queued == 0`).
- **Frontend:** the frontend's hashed assets are immutable. Browsers holding the old `index.html`
  keep working until they reload.

## Pre-deploy checks (manual path, or when something is unusual)
- [ ] CI is green on the commit. Check `docs/release/production-readiness.md` for new blockers.
- [ ] **Migrations in the release are expand-only.**
  - They only add tables, columns or indexes, and new columns are nullable or have defaults.
  - Any rename or drop must have been split across two releases (expand, then contract) so the
    previous release still runs on the new schema.
  - Review: `git diff <current>..<sha> -- backend/alembic/versions`.
- [ ] The pre-deploy backup will run (do not set `SKIP_BACKUP` on the pilot).
- [ ] No incident is in progress. The `BackupFailed`/`BackupStale` alerts are clear.
- [ ] Pilot: release window announced.

## Monitoring after a release (30 minutes)
- `HighServerErrorRate`, `SustainedHighLatency`, `JobFailures` and `EmailDeliveryFailing` stay
  quiet.
- `dc logs --since 30m backend worker | grep '"level": "ERROR"'` shows nothing new.
- Register or reset a password with a test mailbox if the release touched auth or email.
- Spot-check a Hindi screen if the release changed copy.

## Rollback

### Application rollback (the normal case)
```bash
/opt/vanshavali/deploy/pilot/scripts/rollback.sh            # to the previous release
/opt/vanshavali/deploy/pilot/scripts/rollback.sh <sha>      # to a specific earlier release
```
- It pulls the images, recreates the containers, waits for readiness and runs the smoke test.
- **The database is not touched:** the expand-only rule means the older code runs on the newer
  schema.
- Takes 1–2 minutes. Use it for any functional regression.

### Database migration rollback (rare, deliberate)
Only when a migration itself is wrong. Choose one:
1. **`alembic downgrade`:** every migration has a downgrade (CLAUDE.md rule 4).
   - Roll the application back first (rollback.sh), then:
     ```bash
     source deploy/pilot/scripts/lib.sh
     dc --profile release run --rm migrate alembic downgrade <previous revision>
     ```
   - Downgrades that drop columns **lose the data written to them** since the release. Read the
     migration first.
2. **Restore the pre-deploy backup**, when the migration damaged data:
   - It goes into a new empty database; see `backup-restore-runbook.md`.
   - Writes made since the backup are lost, unless you restore with managed PITR to just before
     the migration.
   - This decision needs the owner, and an announcement to pilot users.

Decide using the migration's content. Never "fix forward" a broken schema in production under
time pressure: roll back first.

## Incident communication
- **Who:** the person deploying owns the release until it is verified. The owner (or delegate) is
  the incident lead for anything user-visible.
- **Pilot users:** one message in the pilot group (WhatsApp/email) when the service is down for
  more than 5 minutes, or when data may be affected. Say what is affected and what users should
  do (usually: nothing; don't retry uploads). Send a follow-up when resolved.
- **Record:** a short entry in the incident log (date, release SHA, symptom, cause, fix, data
  impact).
- **Personal-data breach:** follow `incident-response.md` (DPDP Act obligations).
