# Backup, restore and disaster recovery (PRS §55)

Status: runbook written, **restore drill not yet automated** (DEFERRED to Phase 8 hardening).

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

## Drill cadence
Quarterly restore into an isolated environment. Record RPO/RTO achieved. The PRS §55 targets are to
be agreed before production (**BLOCKER for go-live, not for development**).
