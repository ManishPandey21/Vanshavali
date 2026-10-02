#!/usr/bin/env bash
# Encrypted logical backup of the pilot (docs/operations/backup-restore-runbook.md).
#
#   deploy/pilot/scripts/backup.sh [LABEL] [--db-only]
#
# Runs nightly from cron (bootstrap-host.sh installs it) and before every deploy (deploy.sh). It:
#   1. writes a manifest (row counts, alembic version, object totals) before and after the dump;
#   2. pg_dump -Fc as the schema owner, streamed straight into age (public key only on the VM);
#   3. checks the artefact is not plaintext, writes SHA256SUMS;
#   4. uploads dump + manifest + sums to the backup bucket (separate, write-only credentials);
#   5. unless --db-only, copies new document objects into the backup bucket (incremental);
#   6. keeps BACKUP_LOCAL_KEEP_DAYS (7) of local copies; records metrics for the backup alert.
#
# This complements, and does not replace, the managed database's point-in-time recovery: PITR gives
# minutes of RPO inside the provider; this dump survives losing the provider account or region.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

LABEL="nightly"
DB_ONLY=""
for a in "$@"; do
  case "$a" in
    --db-only) DB_ONLY=1 ;;
    -*) die "unknown option $a" ;;
    *) LABEL="$a" ;;
  esac
done
[[ "$LABEL" =~ ^[A-Za-z0-9._-]{1,80}$ ]] || die "bad label '$LABEL'"

for f in app.env migrate.env backup.env; do check_secret_file "$VSH_CONFIG_DIR/$f"; done
load_env "$VSH_CONFIG_DIR/backup.env"
[[ -n "${BACKUP_AGE_RECIPIENT:-}" ]] || die "BACKUP_AGE_RECIPIENT (age public key) is not set in backup.env"
command -v age >/dev/null || die "age is not installed (bootstrap-host.sh installs it)"

TEXTFILE="$VSH_STATE_DIR/textfile/vsh_backup.prom"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
NAME="vanshavali-$STAMP-$LABEL"
DIR="$VSH_STATE_DIR/backups/$NAME"
mkdir -p "$DIR" "$(dirname "$TEXTFILE")"
chmod 700 "$DIR"
started=$SECONDS

metrics() { # metrics STATUS: node-exporter textfile for the BackupFailed / BackupStale alerts
  local tmp="$TEXTFILE.$$"
  {
    echo "# HELP vsh_backup_last_status 1 if the last backup run succeeded."
    echo "# TYPE vsh_backup_last_status gauge"
    echo "vsh_backup_last_status{label=\"$LABEL\"} $1"
    echo "# HELP vsh_backup_last_run_timestamp_seconds When the last backup run finished."
    echo "# TYPE vsh_backup_last_run_timestamp_seconds gauge"
    echo "vsh_backup_last_run_timestamp_seconds{label=\"$LABEL\"} $(date +%s)"
    if [[ "$1" == 1 ]]; then
      echo "# HELP vsh_backup_last_success_timestamp_seconds When the last backup succeeded."
      echo "# TYPE vsh_backup_last_success_timestamp_seconds gauge"
      echo "vsh_backup_last_success_timestamp_seconds $(date +%s)"
      echo "# HELP vsh_backup_last_size_bytes Size of the last encrypted dump."
      echo "# TYPE vsh_backup_last_size_bytes gauge"
      echo "vsh_backup_last_size_bytes $(stat -c %s "$DIR/$NAME.dump.age")"
      echo "# HELP vsh_backup_last_duration_seconds Duration of the last successful backup."
      echo "# TYPE vsh_backup_last_duration_seconds gauge"
      echo "vsh_backup_last_duration_seconds $((SECONDS - started))"
    elif [[ -f "$TEXTFILE" ]]; then
      grep -E '^vsh_backup_last_(success_timestamp|size|duration)' "$TEXTFILE" || true
    fi
  } >"$tmp"
  mv "$tmp" "$TEXTFILE"
}
done_ok=""
trap '[[ -n "$done_ok" ]] || { metrics 0; log "backup FAILED"; }' EXIT

log "backup $NAME"
ops_backup "$DIR" manifest --out manifest-before.json

load_env "$VSH_CONFIG_DIR/migrate.env"
pg_env_from_url "$VSH_DATABASE_URL"
pg_tool pg_dump -Fc --no-owner --no-privileges | age -r "$BACKUP_AGE_RECIPIENT" >"$DIR/$NAME.dump.age"
[[ "$(head -c 21 "$DIR/$NAME.dump.age")" == "age-encryption.org/v1" ]] || die "dump is not age-encrypted"

ops_backup "$DIR" manifest --previous manifest-before.json --out manifest.json
rm -f "$DIR/manifest-before.json"
(cd "$DIR" && sha256sum "$NAME.dump.age" manifest.json >SHA256SUMS)

for f in "$NAME.dump.age" manifest.json SHA256SUMS; do
  ops_backup "$DIR" put "$f" "db/$NAME/$f" >/dev/null
done
log "uploaded db/$NAME ($(stat -c %s "$DIR/$NAME.dump.age") bytes encrypted)"

if [[ -z "$DB_ONLY" ]]; then
  ops_backup "$DIR" mirror-to-backup
fi

find "$VSH_STATE_DIR/backups" -mindepth 1 -maxdepth 1 -type d -mtime +"${BACKUP_LOCAL_KEEP_DAYS:-7}" \
  -exec rm -rf {} +
done_ok=1
metrics 1
if [[ -n "${BACKUP_HEARTBEAT_URL:-}" ]]; then
  curl -fsS -m 10 --retry 3 "$BACKUP_HEARTBEAT_URL" >/dev/null || log "heartbeat ping failed"
fi
log "backup $NAME done in $((SECONDS - started))s"
echo "$NAME"
