# Backup and restore runbook (pilot)

For the pilot topology (ADR-0014). The development-era runbook and the nightly CI drill of the
logical backup are in `backup-restore.md`; this document supersedes its "Restore procedure" for
staging and pilot.

## What protects what

| Layer | Covers | RPO | Kept | Where |
|---|---|---|---|---|
| Managed PITR (WAL) | the database: any point in time | minutes | 7+ days | provider (same account) |
| Managed automated snapshots | the database: daily | 24 h | provider retention | provider |
| **Nightly encrypted dump** (`backup.sh`) | the database, portable to any PostgreSQL 16 | 24 h | 35 days (bucket lifecycle) + 7 days local | **backup bucket, separate account, Object Lock** |
| Pre-deploy dump (`deploy.sh` → `backup.sh pre-<sha> --db-only`) | the database just before a migration | 0 at release time | 35 days | backup bucket |
| Bucket versioning | documents: overwrite or delete mistakes | 0 | 30 days of noncurrent versions | document bucket |
| **Object mirror** (`backup.sh`, nightly) | documents: loss of the bucket or the account | 24 h | 35 days | backup bucket `objects/` |
| Escrow | data keys, age identity, all config | — | indefinitely | offline (secrets-management.md) |

- **Restorable from these alone:** everything except the data keys and the age identity. Without
  the escrowed keys, restored documents cannot be decrypted (ADR-0004).
- **What the VM holds:** only Redis' queue, which is lost-able by design.

## Backup procedure (automatic; manual when needed)
- **Schedule:** cron runs `deploy/pilot/scripts/backup.sh nightly` at 20:41 UTC (02:11 IST), as
  the deploy user.
- **Manual run:** `backup.sh manual` (full) or `backup.sh <label> --db-only`.

Each run:
1. **Manifest before:** row counts of every table (as the owner, since RLS hides rows from the
   app role), the alembic version, and the bucket's object count and bytes.
2. **Dump:** `pg_dump -Fc --no-owner --no-privileges` as the schema owner, streamed straight into
   `age -r <recipient>`. The plaintext never touches the disk. The script checks that the file
   starts with the age header.
3. **Manifest after:** the dump's snapshot lies between the two manifests, so a restore is checked
   against that range even while users write.
4. **Checksums:** `SHA256SUMS` over the dump and the manifest.
5. **Upload:** to `s3://<backup bucket>/db/<name>/`, with credentials that cannot delete.
6. **Object mirror:** documents not yet in `objects/` are copied, incrementally; objects are
   write-once.
7. **Housekeeping and metrics:**
   - local copies older than 7 days are removed;
   - `vsh_backup_*` metrics are written for the alerts (`BackupFailed`, `BackupStale`);
   - the optional heartbeat URL is pinged.

Logs go to `/var/lib/vanshavali/backup.log`. List backups:
`source deploy/pilot/scripts/lib.sh && ops_backup /tmp ls db/`.

## Restore procedure

### Which restore?
| Situation | Use |
|---|---|
| Bad migration, accidental mass edit, corruption noticed within PITR window | **Managed PITR** to a new instance at a time just before the event (fastest, smallest RPO); then point the app at it |
| Provider instance lost and PITR unavailable; account compromise; provider exit | **Dump restore** (below) into any PostgreSQL 16 |
| A few documents deleted or overwritten | Bucket **versioning**: restore the previous version |
| Document bucket lost | `ops_backup mirror-from-backup` into a new bucket (part of the dump restore with `--objects`) |
| Whole environment lost | New VM (`bootstrap-host.sh`) + escrowed config + dump restore `--objects` + `deploy.sh` |

### Dump restore into a clean environment
Prerequisites:
- an **empty** PostgreSQL 16 database (`pg_trgm` and `unaccent` available) with the schema owner
  role;
- an **empty** document bucket;
- the VM's config pointing at both (`migrate.env`, `app.env`), with the **same data keys** as the
  source environment (from escrow);
- the age **identity** file, fetched from escrow onto the VM for the duration of the restore.

```bash
cd /opt/vanshavali && source deploy/pilot/scripts/lib.sh
ops_backup /tmp ls db/                                   # pick the backup, e.g. vanshavali-20261002T204100Z-nightly
deploy/pilot/scripts/restore.sh vanshavali-20261002T204100Z-nightly --identity /root/backup.key --objects
SKIP_BACKUP=1 deploy/pilot/scripts/deploy.sh <current sha>   # starts the stack; readiness + full smoke test
dc run --rm ... # or from your workstation:
SMOKE_PASSWORD=... python -m app.cli.smoke --base-url https://<domain> --email <smoke account> --verify-existing "<a tree that existed before the backup>"
shred -u /root/backup.key                                # the identity goes back to escrow only
```

`restore.sh` then:
1. **Fetches and verifies:** downloads the three files, checks `SHA256SUMS`, and refuses a damaged
   backup.
2. **Refuses** a target database that has any table in `public`. It never restores over data.
3. **Restores the database:** `age -d | pg_restore --no-owner --no-privileges --exit-on-error`.
4. **Migrates:** `alembic upgrade head`, which also applies any newer migrations, then
   `ensure_app_role`, which creates the RLS-bound app role and grants. Roles are not in the dump.
5. **Restores objects** (`--objects`): copies the mirror into the bucket.
6. **Verifies** (`check-restore`):
   - every table's row count lies within the manifest's before/after range;
   - the alembic version matches;
   - the object count is at least the manifest's;
   - `audit_event` still rejects UPDATE and DELETE (append-only trigger).
7. **Reports:** writes `/var/lib/vanshavali/last-restore.json` with per-step timings.

**Manual steps that remain** (not automatable here):
- provision the database and bucket;
- fetch the identity from escrow;
- update DNS if the VM changed;
- decide which backup to use;
- tell pilot users about the data-loss window.

## Drill (executed 2 Oct 2026, sandbox)
Reproducible with `deploy/pilot/drill/run-drill.sh`. It runs the **real** `compose.yml`,
`Caddyfile`, `deploy.sh`, `backup.sh` and `restore.sh`, plus the smoke test. Stand-ins:
- the managed database: PostgreSQL 16 with a non-superuser `CREATEROLE` owner, like a managed
  instance;
- the buckets: moto S3 API with versioning;
- SMTP: a sink that **requires** STARTTLS.

Report: `docs/release/evidence/pilot-2026-10-02/drill-report.json`; log: `drill-2026-10-02.log`.

| Phase | What happened | Result | Time |
|---|---|---|---|
| A. Deploy | config + keys generated, stand-ins up, buckets created, `deploy.sh` (migrations as non-superuser owner, `ensure_app_role`, 2 backend + 2 worker replicas, readiness) | ✅ | 59.4 s (first boot incl. ClamAV signature load) |
| B. Email | register via the API → worker → SMTP **STARTTLS** → sink → follow the verification link | ✅ | 1.6 s |
| C. Data | smoke test 13/13 kept as "Restore drill" (2 people, photo, GEDZIP import with photo, property, property document) + synthetic tree of **10,000 people** | ✅ | 14.3 s |
| D. Backup | manifest, encrypted dump (2.1 MB), checksums, upload, object mirror (10 objects) | ✅ | 10.2 s |
| E. Writes after backup | another smoke tree, "After backup" | (control) | — |
| F. Disaster | all app containers, the **database volume**, Redis volume and **every version of every object in the primary bucket** destroyed; empty DB and bucket recreated | — | 7.1 s |
| G1. Restore data | fetch 4.2 s · `pg_restore` 2.0 s · migrate + app role 3.9 s · objects 1.5 s · verify 1.8 s: **42 tables, 60,058 rows = manifest; 10 objects; audit append-only (UPDATE and DELETE rejected)** | ✅ | 13.9 s |
| G2. Start stack | `deploy.sh` (readiness of every replica) | ✅ | 52.9 s |
| G3. Verify | `smoke --verify-existing "Restore drill"` 9/9: health + RLS, SPA, **login**, tree, people (incl. imported), **property records**, **photo and document download with matching SHA-256** (data keys + restored objects), **GEDCOM export**, **audit trail** | ✅ | 1.9 s |
| — | "After backup" tree **absent**: the restore came from the backup, and the RPO boundary is real | ✅ | — |
| G4. New writes | full smoke test on the restored site (incl. GEDZIP import) 14/14 | ✅ | 1.9 s |

**Measured:**
- **RTO, disaster → verified service:** 75.8 s (sandbox).
- **Data-loss window:** everything after the dump's snapshot. In the drill that was 9 s; in
  production it is the time since the last nightly dump (≤ 24 h), or minutes with PITR.

**Defect found and fixed by this drill:** `ensure_app_role` failed on every deploy after the first
when the schema owner is not a superuser, as on managed PostgreSQL (`3dea906`, regression test
`test_app_role.py`). No earlier test had a non-superuser owner.

**Limitations (be explicit):**
- One shared 4-vCPU sandbox; the stand-ins are not the managed services. Not exercised:
  - provider PITR;
  - provider snapshot restore;
  - S3 Object Lock;
  - cross-account permissions;
  - DNS changes;
  - real network transfer times.
- The OCR binary was absent from the drill image (no Debian mirror access in the sandbox), so
  `VSH_OCR_ENABLED=false`. OCR is covered by the backend tests and the earlier performance work.
- **A real RTO is dominated by provisioning and human steps** (new instance, fetching the
  identity, DNS), so budget hours, not seconds.

### Targets to agree (go-live checklist)
Proposed: **RPO ≤ 15 min** (PITR), and ≤ 24 h in the worst case (provider loss → dump);
**RTO ≤ 4 h** for a full-environment rebuild. Confirm them by running this drill on the staging
environment against **real** managed services. Record the measured numbers in
`production-readiness.md`.

### Cadence
- **Nightly (CI):** `.github/workflows/drill.yml`, logical backup/restore of a 10k tree (unchanged).
- **Quarterly (staging):** `run-drill.sh`, or the same steps by hand against the real managed
  services, plus one PITR restore into a scratch instance.
- **After any change** to `backup.sh`, `restore.sh`, migrations tooling or keys: one staging
  restore.
