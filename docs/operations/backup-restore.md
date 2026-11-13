# Backup, restore and disaster recovery (PRS §55)

Status: runbook written; **restore drill automated** (`ops/backup/drill.sh` + `ops/backup/verify.py`,
nightly/manual workflow `.github/workflows/drill.yml`) and run end to end locally on 25 Sep 2026
(results below). The drill covers the logical backup and the local object store. PITR/WAL restore,
S3 object versions and cross-region copies are managed-service features that the drill does not
exercise. RPO/RTO targets are still to be agreed (see "Drill cadence").

## What must be backed up
| Asset | Where | Method |
|---|---|---|
| Canonical data | PostgreSQL | Managed PITR (WAL archiving) + nightly `pg_dump -Fc`, encrypted, stored off-site |
| Document originals and derivatives | S3/MinIO bucket `vanshavali` | Bucket versioning + object lock (governance mode) + cross-region replication |
| Encryption keys (`VSH_STANDARD_DATA_KEY`, `VSH_VAULT_DATA_KEY`) | Secret manager | Escrowed separately. **Losing these makes every stored document unreadable.** |
| Signing key | Secret manager | Rotatable. Rotating it only invalidates outstanding download links. |

Objects are encrypted by the app (AES-256-GCM, ADR-0004), so bucket backups are ciphertext.
Database dumps contain personal data and must be encrypted (`age`/`gpg` or KMS) before leaving
the primary region.

## Nightly logical backup (example)
```bash
pg_dump -Fc "$DATABASE_URL" | age -r "$BACKUP_RECIPIENT" > vanshavali-$(date +%F).dump.age
sha256sum vanshavali-*.dump.age > SHA256SUMS
```

## Restore procedure
1. Provision an empty PostgreSQL 16 instance with the `pg_trgm` and `unaccent` extensions available.
2. `age -d -i key.txt vanshavali-DATE.dump.age | pg_restore -d "$NEW_DATABASE_URL" --no-owner`.
3. `cd backend && VSH_DATABASE_URL=$NEW_DATABASE_URL uv run alembic upgrade head` (a no-op if the
   dump is at head; it applies any newer migrations).
4. Point the app at the restored bucket version (or restore objects by version id), and at the
   same data keys.
5. Verify: `GET /api/v1/health`; log in as a known user; open a tree; download one STANDARD and one
   VAULT document (this proves both keys work); check that `audit_event` row counts match the
   backup manifest.

With RLS (ADR-0002), the restored database also needs the non-owner application role:
`pg_restore --no-privileges` skips grants that name cluster roles. Then run
`python -m app.cli.ensure_app_role` as the owner, after `alembic upgrade head`. Row counts and
dumps must use the owner or a superuser, because RLS filters every other role.

## Automated restore drill
```bash
ops/backup/drill.sh                          # age (ephemeral key) if installed, else openssl
DRILL_ENCRYPTION=openssl DRILL_PASSPHRASE=… DRILL_PEOPLE=10000 ops/backup/drill.sh
```
The drill runs these steps (full options are in the script header):
1. **Seed** a fresh source database `vsh_drill_src` and a fresh storage directory
   (`ops/backup/seed_source.py`): `alembic upgrade head`, the demo tree, a synthetic tree of
   `DRILL_PEOPLE` people (`benchmark.build`), and one STANDARD photo and one VAULT birth
   certificate uploaded through the API.
   The demo login's password comes only from `VSH_DEMO_PASSWORD`. `drill.sh` generates a random
   one per run, and you must set it yourself with `DRILL_SKIP_SEED=1`. It is never written to the
   manifest or printed.
2. **Back up:**
   - `pg_dump -Fc`, piped straight into `age` (or `openssl enc -aes-256-cbc -pbkdf2 -iter 200000`
     with the passphrase read from `env:DRILL_PASSPHRASE`, never from argv);
   - a tar of the object-store directory, encrypted the same way;
   - `SHA256SUMS`;
   - a check that the dump artefact is not plaintext.
3. **Restore:**
   - verify the checksums;
   - decrypt and `pg_restore --no-owner --no-privileges --exit-on-error` into a fresh
     `vsh_drill_dst`;
   - untar into a fresh storage directory;
   - `alembic upgrade head`;
   - `ensure_app_role` (drill role `vsh_drill_app`) when the codebase has RLS.
4. **Verify** (`ops/backup/verify.py`; the exit status fails the drill):
   - row counts match for every table in `public` (38 tables at head), and so does
     `alembic_version`;
   - the demo user logs in through the API (TestClient on the restored database and storage, as
     the app role when RLS is on);
   - the STANDARD and VAULT documents download through the signed-URL flow and their sha256 matches
     `document.checksum_sha256`, which proves both data keys decrypt the restored objects;
   - `UPDATE` and `DELETE` on `audit_event` are still rejected by the append-only trigger (apart
     from erasing IP and browser on entries over a year old, ADR-0033).

Negative control: `verify.py` run with a different `VSH_VAULT_DATA_KEY` reports
`[FAIL] download VAULT document … file 500, sha256 match False` and exits 1. It must run against
a freshly restored database: its own login writes `audit_event` and `user_session` rows, so a
second run reports count mismatches for those two tables.

### Results: 25 Sep 2026, dev container (4 vCPU, PostgreSQL 16 local, other workloads running)
| Run | Rows (38 tables) | Encrypted dump | pg_dump + storage copy | pg_restore | storage restore | alembic | verify | **Restore + verify** |
|---|---|---|---|---|---|---|---|---|
| age, 10k people + demo | 60,137 | 2.10 MB (+62 kB objects) | 0.41 s | 1.80 s | 0.02 s | 1.21 s | 3.60 s | **6.7 s** |
| openssl, 10k people + demo | 60,137 | 2.10 MB (+61 kB objects) | 0.64 s | 1.62 s | 0.15 s | 1.03 s | 3.14 s | **5.9 s** |
| age, 500 people, working tree with RLS + app role | 3,137 (39 tables) | — | — | — | — | — | 2.6 s | all checks PASS |

The first two rows ran on commit `06d0ced`; the third ran on the uncommitted RLS work (alembic
`c4e8f1a2b3d5`), which confirms the drill works with `ensure_app_role`.

How to read these numbers:
- **RPO** of this mechanism alone is the backup interval: nightly `pg_dump` means up to 24 h of
  lost writes. The recovery point is the moment `pg_dump` takes its snapshot (recorded as
  `recovery_point_utc` in `drill-report.json`). Managed PITR (WAL archiving) is what brings the
  database RPO down to minutes. Object-store RPO depends on bucket replication lag.
- **RTO** measured here is about 6–7 s for a 10k-person tree. That time is dominated by fixed
  costs (Python start-up, `alembic`, the TestClient app); only `pg_restore` grows with data. A real
  restore adds instance provisioning, transfer of the artefact from off-site storage, DNS/secret
  changes and the human decision time, and these dominate: budget in hours, not seconds, until a
  full-environment drill has been timed.
- The dump is about 35 bytes per row compressed. Extrapolated linearly, 1M rows is about 70 MB and
  restores in about 1 min on similar hardware (**ASSUMPTION**, not measured).

## Drill cadence
Nightly automated drill in CI (`.github/workflows/drill.yml`: Postgres 16 service, 10k people,
age by default, `workflow_dispatch` inputs for size and encryption). The job summary holds the
timings and the report JSON is uploaded as an artefact. The encrypted dump and key never leave the
runner. Quarterly, restore a real backup into an isolated environment and record the RPO/RTO
achieved end to end (provisioning included). The PRS §55 targets are to be agreed before
production (**BLOCKER for go-live, not for development**).
