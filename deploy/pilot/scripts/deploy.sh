#!/usr/bin/env bash
# Deploy one release of the pilot stack (docs/operations/release-runbook.md).
#
#   deploy/pilot/scripts/deploy.sh <version>        # version = the image tag (the git commit SHA)
#
# Steps:
#   1. preflight (config files and modes, images pull; SKIP_PULL=1 for locally built images)
#   2. pre-deploy backup (encrypted pg_dump; skipped with SKIP_BACKUP=1)
#   3. migrations as the schema owner + application role/grants (expand-only, ADR-0002)
#   4. start the new containers
#   5. readiness on every backend replica (DB, Redis, RLS in force)
#   6. smoke test through Caddy (skipped with SKIP_SMOKE=1)
#   7. record the release
#
# If 5 or 6 fails, the previous application version is started again automatically (the database is
# not rolled back: migrations are backward compatible with the previous release by rule). Set
# NO_AUTO_ROLLBACK=1 to leave the failed release running for diagnosis.
#
# Over SSH from CI the deploy user's authorized_keys entry forces this script, e.g.
#   command="/opt/vanshavali/deploy/pilot/scripts/deploy.sh \"$SSH_ORIGINAL_COMMAND\"",restrict ssh-ed25519 ...
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

VERSION="${1:-}"
[[ "$VERSION" =~ ^[A-Za-z0-9._-]{1,128}$ ]] || die "usage: deploy.sh <image tag>, got '${VERSION}'"
exec 9>"$VSH_STATE_DIR/deploy.lock"
flock -n 9 || die "another deploy is running"

load_env "$VSH_CONFIG_DIR/compose.env"
for f in app.env migrate.env; do check_secret_file "$VSH_CONFIG_DIR/$f"; done
PREVIOUS="$(current_version)"
log "deploying $VERSION (current: ${PREVIOUS:-none})"
started=$SECONDS

rollback() {
  log "FAILED: $1"
  if [[ -n "${NO_AUTO_ROLLBACK:-}" || -z "$PREVIOUS" ]]; then
    die "left $VERSION running for diagnosis (no automatic rollback)"
  fi
  log "rolling the application back to $PREVIOUS (database unchanged)"
  VSH_VERSION="$PREVIOUS" dc up -d --remove-orphans
  VSH_VERSION="$PREVIOUS" wait_ready 180 || log "previous release is not ready either: see docs/operations/incident-response.md"
  die "deploy of $VERSION failed; $PREVIOUS restored"
}

log "1/7 preflight"
VSH_VERSION="$VERSION" dc config -q
if [[ -z "${SKIP_PULL:-}" ]]; then # SKIP_PULL=1 only for images built on this machine (drills)
  VSH_VERSION="$VERSION" dc --profile release pull --quiet backend frontend migrate
fi

if [[ -z "${SKIP_BACKUP:-}" && -n "$PREVIOUS" ]]; then
  log "2/7 pre-deploy backup"
  "$DEPLOY_DIR/scripts/backup.sh" "pre-$VERSION" --db-only
else
  log "2/7 pre-deploy backup skipped (${SKIP_BACKUP:+SKIP_BACKUP set}${PREVIOUS:-first deploy})"
fi

log "3/7 migrations (schema owner) and application role"
VSH_VERSION="$VERSION" dc --profile release run --rm migrate

log "4/7 start $VERSION"
VSH_VERSION="$VERSION" dc up -d --remove-orphans --wait --wait-timeout 600 ||
  rollback "containers did not start healthy"

log "5/7 readiness"
VSH_VERSION="$VERSION" wait_ready 240 || rollback "backend replicas did not become ready"

if [[ -z "${SKIP_SMOKE:-}" ]]; then
  log "6/7 smoke test"
  VSH_VERSION="$VERSION" run_smoke || rollback "smoke test failed"
else
  log "6/7 smoke test skipped (SKIP_SMOKE set)"
fi

log "7/7 record release"
mkdir -p "$VSH_STATE_DIR/release"
[[ -n "$PREVIOUS" && "$PREVIOUS" != "$VERSION" ]] && echo "$PREVIOUS" >"$VSH_STATE_DIR/release/previous"
echo "$VERSION" >"$VSH_STATE_DIR/release/current"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $VERSION (from ${PREVIOUS:-none}) in $((SECONDS - started))s" \
  >>"$VSH_STATE_DIR/release/history"
log "deployed $VERSION in $((SECONDS - started))s"
