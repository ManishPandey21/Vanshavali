#!/usr/bin/env bash
# Backup/restore drill (PRS §55; docs/operations/backup-restore.md).
#
# End to end, against a local PostgreSQL 16 superuser and the local object store:
#   1. seed     fresh SOURCE database (migrated) + storage dir: demo tree, a synthetic tree
#               (DRILL_PEOPLE people) and one STANDARD + one VAULT document   [skip: DRILL_SKIP_SEED=1]
#   2. backup   pg_dump -Fc of the source and a tar of the storage dir, each encrypted
#               (age if installed, else openssl enc -aes-256-cbc -pbkdf2), plus SHA256SUMS
#   3. restore  checksum check -> decrypt -> pg_restore into a FRESH database, untar into a FRESH
#               storage dir -> alembic upgrade head
#   4. verify   ops/backup/verify.py: per-table row counts, API login, STANDARD+VAULT download with
#               sha256 check, audit_event append-only trigger
# and prints RPO/RTO-style timings (also written to $DRILL_WORK/drill-report.json).
#
# Usage (from the repo root; needs uv, pg_dump/pg_restore/createdb/dropdb 16, tar, and age or openssl):
#   ops/backup/drill.sh
#
# Environment:
#   PGHOST PGPORT PGUSER PGPASSWORD   connection (default localhost 5432 vanshavali vanshavali)
#   DRILL_SRC_DB / DRILL_DST_DB       database names (default vsh_drill_src / vsh_drill_dst).
#                                     BOTH ARE DROPPED AND RECREATED (source only when seeding).
#   DRILL_WORK                        working dir for artefacts (default: a new mktemp -d)
#   DRILL_SRC_STORAGE                 source object-store dir (default $DRILL_WORK/storage-src)
#   DRILL_PEOPLE                      synthetic tree size for the seed (default 2000)
#   VSH_DEMO_PASSWORD                 seeded login's password; generated per run when seeding, and
#                                     REQUIRED with DRILL_SKIP_SEED=1 (the password of the manifest's
#                                     account). Never written to the manifest or printed.
#   DRILL_ENCRYPTION                  age | openssl (default: age if installed, else openssl)
#   DRILL_AGE_RECIPIENT               age public key; if unset an ephemeral identity is generated
#   DRILL_AGE_IDENTITY                age private key file for decryption (with DRILL_AGE_RECIPIENT)
#   DRILL_PASSPHRASE                  openssl passphrase (required for openssl; read via env:, never argv)
#   VSH_STANDARD_DATA_KEY / VSH_VAULT_DATA_KEY  must be the keys the source used (dev keys by default)
#   DRILL_APP_ROLE                    non-owner app role for the restored DB when the codebase has
#                                     app/cli/ensure_app_role.py (RLS, ADR-0002); default vsh_drill_app.
#                                     Roles are cluster-wide: never reuse the production role name on a
#                                     shared cluster, because its password is (re)set by the drill.
#
# Real backups: point DRILL_SKIP_SEED=1 and DRILL_SRC_DB/DRILL_SRC_STORAGE at a *copy* you may read,
# keep the age identity / passphrase in the secret manager, and never write artefacts to shared disks.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PGHOST="${PGHOST:-localhost}" PGPORT="${PGPORT:-5432}"
export PGUSER="${PGUSER:-vanshavali}" PGPASSWORD="${PGPASSWORD:-vanshavali}"
SRC_DB="${DRILL_SRC_DB:-vsh_drill_src}"
DST_DB="${DRILL_DST_DB:-vsh_drill_dst}"
WORK="${DRILL_WORK:-$(mktemp -d -t vsh-drill.XXXXXX)}"
SRC_STORAGE="${DRILL_SRC_STORAGE:-$WORK/storage-src}"
DST_STORAGE="$WORK/storage-restored"
PEOPLE="${DRILL_PEOPLE:-2000}"
mkdir -p "$WORK" "$SRC_STORAGE"
chmod 700 "$WORK"
umask 077

url() { echo "postgresql+psycopg://$PGUSER:$PGPASSWORD@$PGHOST:$PGPORT/$1"; }
SRC_URL="$(url "$SRC_DB")"
DST_URL="$(url "$DST_DB")"
now() { date +%s.%N; }
secs() { awk -v a="$1" -v b="$2" 'BEGIN { printf "%.2f", b - a }'; }
log() { printf '\n== %s\n' "$*"; }
if [[ "$SRC_DB" == "$DST_DB" ]]; then echo "source and restore database must differ" >&2; exit 2; fi

# ---- encryption: age (preferred) or openssl
ENC="${DRILL_ENCRYPTION:-}"
if [[ -z "$ENC" ]]; then
  if command -v age >/dev/null 2>&1; then ENC=age; else ENC=openssl; fi
fi
case "$ENC" in
  age)
    if [[ -z "${DRILL_AGE_RECIPIENT:-}" ]]; then
      age-keygen -o "$WORK/age-identity.txt" 2>/dev/null
      DRILL_AGE_IDENTITY="$WORK/age-identity.txt"
      DRILL_AGE_RECIPIENT="$(age-keygen -y "$DRILL_AGE_IDENTITY")"
    fi
    : "${DRILL_AGE_IDENTITY:?DRILL_AGE_IDENTITY is required with DRILL_AGE_RECIPIENT}"
    encrypt() { age -r "$DRILL_AGE_RECIPIENT"; }
    decrypt() { age -d -i "$DRILL_AGE_IDENTITY"; }
    EXT=age
    ;;
  openssl)
    : "${DRILL_PASSPHRASE:?set DRILL_PASSPHRASE for openssl encryption}"
    export DRILL_PASSPHRASE
    encrypt() { openssl enc -aes-256-cbc -pbkdf2 -iter 200000 -salt -pass env:DRILL_PASSPHRASE; }
    decrypt() { openssl enc -d -aes-256-cbc -pbkdf2 -iter 200000 -pass env:DRILL_PASSPHRASE; }
    EXT=enc
    ;;
  *) echo "DRILL_ENCRYPTION must be age or openssl" >&2; exit 2 ;;
esac

cd "$ROOT/backend"
export VSH_JOB_MODE=sync VSH_STORAGE_BACKEND=local VSH_OCR_ENABLED=false
if [[ "${DRILL_SKIP_SEED:-0}" == "1" ]]; then
  : "${VSH_DEMO_PASSWORD:?set VSH_DEMO_PASSWORD to the password of the manifest account}"
elif [[ -z "${VSH_DEMO_PASSWORD:-}" ]]; then
  VSH_DEMO_PASSWORD="$(openssl rand -base64 24)"
fi
export VSH_DEMO_PASSWORD

# ---- 1. seed
T_SEED=0
if [[ "${DRILL_SKIP_SEED:-0}" != "1" ]]; then
  log "1/4 seed source database $SRC_DB ($PEOPLE synthetic people + demo tree + 2 documents)"
  t0=$(now)
  dropdb --if-exists "$SRC_DB"; createdb "$SRC_DB"
  rm -rf "$SRC_STORAGE"; mkdir -p "$SRC_STORAGE"
  VSH_DATABASE_URL="$SRC_URL" uv run --quiet alembic upgrade head
  VSH_DATABASE_URL="$SRC_URL" VSH_STORAGE_LOCAL_PATH="$SRC_STORAGE" \
    uv run --quiet python "$ROOT/ops/backup/seed_source.py" --people "$PEOPLE" --manifest "$WORK/manifest.json"
  T_SEED=$(secs "$t0" "$(now)")
fi
[[ -f "$WORK/manifest.json" ]] || { echo "no $WORK/manifest.json (needed by verify.py)" >&2; exit 2; }

# ---- 2. backup (the moment pg_dump takes its snapshot is the recovery point)
log "2/4 backup ($ENC)"
t0=$(now)
RECOVERY_POINT="$(date -u +%FT%TZ)"
pg_dump -Fc --no-owner "$SRC_DB" | encrypt >"$WORK/db.dump.$EXT"
T_DUMP=$(secs "$t0" "$(now)")
t1=$(now)
tar -C "$SRC_STORAGE" -cf - . | encrypt >"$WORK/storage.tar.$EXT"
T_STORAGE_BACKUP=$(secs "$t1" "$(now)")
(cd "$WORK" && sha256sum "db.dump.$EXT" "storage.tar.$EXT" >SHA256SUMS)
T_BACKUP=$(secs "$t0" "$(now)")
DUMP_BYTES=$(stat -c %s "$WORK/db.dump.$EXT")
STORAGE_BYTES=$(stat -c %s "$WORK/storage.tar.$EXT")
echo "db.dump.$EXT $DUMP_BYTES bytes, storage.tar.$EXT $STORAGE_BYTES bytes, backup ${T_BACKUP}s"
# the plaintext must not be recoverable from the artefact
if head -c 5 "$WORK/db.dump.$EXT" | grep -q PGDMP; then echo "dump is not encrypted" >&2; exit 1; fi

# ---- 3. restore into fresh targets
log "3/4 restore into fresh database $DST_DB and fresh storage dir"
t0=$(now)
(cd "$WORK" && sha256sum --quiet -c SHA256SUMS)
dropdb --if-exists "$DST_DB"; createdb "$DST_DB"
# --no-privileges: grants name cluster roles that may not exist here; they are re-applied below
decrypt <"$WORK/db.dump.$EXT" | pg_restore --no-owner --no-privileges --exit-on-error -d "$DST_DB"
T_PGRESTORE=$(secs "$t0" "$(now)")
t1=$(now)
rm -rf "$DST_STORAGE"; mkdir -p "$DST_STORAGE"
decrypt <"$WORK/storage.tar.$EXT" | tar -C "$DST_STORAGE" -xf -
T_STORAGE_RESTORE=$(secs "$t1" "$(now)")
t1=$(now)
VSH_DATABASE_URL="$DST_URL" uv run --quiet alembic upgrade head
API_URL="$DST_URL"
if [[ -f app/cli/ensure_app_role.py ]]; then
  # RLS: the API must run as a non-owner role, so verify.py logs in and downloads through it
  APP_ROLE="${DRILL_APP_ROLE:-vsh_drill_app}"
  APP_PW="$(openssl rand -hex 16)"
  VSH_DATABASE_URL="$DST_URL" VSH_APP_DB_ROLE="$APP_ROLE" VSH_APP_DB_PASSWORD="$APP_PW" \
    uv run --quiet python -m app.cli.ensure_app_role
  API_URL="postgresql+psycopg://$APP_ROLE:$APP_PW@$PGHOST:$PGPORT/$DST_DB"
fi
T_MIGRATE=$(secs "$t1" "$(now)")
T_RESTORE=$(secs "$t0" "$(now)")
echo "pg_restore ${T_PGRESTORE}s, storage ${T_STORAGE_RESTORE}s, alembic ${T_MIGRATE}s"

# ---- 4. verify
log "4/4 verify"
t0=$(now)
set +e
uv run --quiet python "$ROOT/ops/backup/verify.py" --source-url "$SRC_URL" --restored-url "$DST_URL" \
  --api-url "$API_URL" --storage "$DST_STORAGE" --manifest "$WORK/manifest.json" --report "$WORK/verify.json"
VERIFY_RC=$?
set -e
T_VERIFY=$(secs "$t0" "$(now)")
RTO=$(awk -v a="$T_RESTORE" -v b="$T_VERIFY" 'BEGIN { printf "%.2f", a + b }')

cat >"$WORK/drill-report.json" <<JSON
{
  "encryption": "$ENC",
  "recovery_point_utc": "$RECOVERY_POINT",
  "people_seeded": $PEOPLE,
  "seconds": {
    "seed": $T_SEED,
    "backup_total": $T_BACKUP, "pg_dump": $T_DUMP, "storage_backup": $T_STORAGE_BACKUP,
    "restore_total": $T_RESTORE, "pg_restore": $T_PGRESTORE, "storage_restore": $T_STORAGE_RESTORE,
    "alembic_upgrade": $T_MIGRATE, "verify": $T_VERIFY, "rto_restore_plus_verify": $RTO
  },
  "bytes": { "db_dump_encrypted": $DUMP_BYTES, "storage_encrypted": $STORAGE_BYTES },
  "verify_ok": $([[ $VERIFY_RC -eq 0 ]] && echo true || echo false)
}
JSON
log "summary"
cat "$WORK/drill-report.json"
echo "artefacts in $WORK (contain personal data in production: shred after the drill)"
exit $VERIFY_RC
