#!/usr/bin/env bash
# Restore a backup into an EMPTY database and bucket (docs/operations/backup-restore-runbook.md).
#
#   deploy/pilot/scripts/restore.sh <backup name | local dir> --identity /path/to/age-key.txt [--objects]
#
# <backup name> is a folder under db/ in the backup bucket (e.g. vanshavali-20261002T024100Z-nightly;
# list them with: ops_backup ls db/), or a local directory holding the same three files.
#
# The target is whatever $VSH_CONFIG_DIR describes: migrate.env (owner URL of the empty target
# database) and app.env (target primary bucket and the SAME data keys as the source; ADR-0004: other
# keys cannot decrypt the objects). For a restore drill point VSH_CONFIG_DIR at a drill config dir.
#
# Steps (each timed):
#   1. fetch from the backup bucket, verify SHA256SUMS
#   2. age -d | pg_restore --no-owner --no-privileges --exit-on-error into the empty target
#   3. alembic upgrade head + ensure_app_role (the migrate service)
#   4. --objects: copy backup:objects/ into the target bucket
#   5. check-restore: row counts within the manifest's range, object count, audit log append-only
# Then start the stack (deploy.sh <version> with SKIP_BACKUP=1) and run the smoke test in
# --verify-existing mode against a tree created before the backup.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

SRC="" IDENTITY="" OBJECTS=""
while (($#)); do
  case "$1" in
    --identity) IDENTITY="$2"; shift 2 ;;
    --objects) OBJECTS=1; shift ;;
    -*) die "unknown option $1" ;;
    *) SRC="$1"; shift ;;
  esac
done
[[ -n "$SRC" && -r "$IDENTITY" ]] || die "usage: restore.sh <backup name|dir> --identity KEYFILE [--objects]"
for f in app.env migrate.env backup.env; do check_secret_file "$VSH_CONFIG_DIR/$f"; done
VSH_VERSION="${VSH_VERSION:-$(current_version)}"
[[ -n "$VSH_VERSION" ]] || die "set VSH_VERSION to the image tag to restore with"
export VSH_VERSION

declare -A T
t() { T[$1]=$(( $(date +%s%N) / 1000000 - $2 )); }
now() { echo $(( $(date +%s%N) / 1000000 )); }
total=$(now)

WORK="$(mktemp -d "$VSH_STATE_DIR/restore.XXXXXX")"
chmod 700 "$WORK"
trap 'rm -rf "$WORK"' EXIT

s=$(now)
if [[ -d "$SRC" ]]; then
  cp "$SRC"/* "$WORK/"
else
  [[ "$SRC" =~ ^[A-Za-z0-9._-]+$ ]] || die "bad backup name '$SRC'"
  for f in manifest.json SHA256SUMS; do ops_backup "$WORK" get "db/$SRC/$f" "$f" >/dev/null; done
  ops_backup "$WORK" get "db/$SRC/$SRC.dump.age" "$SRC.dump.age" >/dev/null
fi
(cd "$WORK" && sha256sum -c --quiet SHA256SUMS) || die "checksum mismatch: the backup is damaged"
DUMP="$(ls "$WORK"/*.dump.age)"
t fetch "$s"
log "fetched and verified $(basename "$DUMP") ($(stat -c %s "$DUMP") bytes)"

load_env "$VSH_CONFIG_DIR/migrate.env"
pg_env_from_url "$VSH_DATABASE_URL"
tables="$(pg_tool psql -XAtc "select count(*) from information_schema.tables where table_schema='public'")"
[[ "$tables" == 0 ]] || die "target database $PGDATABASE on $PGHOST is not empty ($tables tables): refusing to restore over data"

s=$(now)
age -d -i "$IDENTITY" "$DUMP" | pg_tool pg_restore --no-owner --no-privileges --exit-on-error -d "$PGDATABASE"
t pg_restore "$s"
log "database restored"

s=$(now)
dc --profile release run --rm migrate
t migrate "$s"

if [[ -n "$OBJECTS" ]]; then
  s=$(now)
  ops_backup "$WORK" mirror-from-backup
  t objects "$s"
fi

s=$(now)
ops_backup "$WORK" check-restore --manifest manifest.json
t verify "$s"
t total "$total"

recovery_point="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["taken_at_utc"])' "$WORK/manifest.json")"
{
  printf '{"backup": "%s", "recovery_point_utc": "%s", "restored_at_utc": "%s", "ms": {' \
    "$(basename "$DUMP" .dump.age)" "$recovery_point" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  sep=""
  for k in fetch pg_restore migrate objects verify total; do
    [[ -n "${T[$k]:-}" ]] && printf '%s"%s": %s' "$sep" "$k" "${T[$k]}" && sep=", "
  done
  printf '}}\n'
} | tee "$VSH_STATE_DIR/last-restore.json"
log "restore complete; next: start the stack and run the smoke test with --verify-existing"
