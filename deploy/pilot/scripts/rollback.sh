#!/usr/bin/env bash
# Roll the application back to an earlier release (docs/operations/release-runbook.md, "Rollback").
#
#   deploy/pilot/scripts/rollback.sh             # to the previous release
#   deploy/pilot/scripts/rollback.sh <version>   # to a specific image tag
#
# The database is NOT touched: migrations are expand-only, so the previous release runs on the newer
# schema. A schema rollback is a separate, deliberate decision (alembic downgrade or a restore from the
# pre-deploy backup) described in the runbook.
set -euo pipefail
# shellcheck source=lib.sh
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

TARGET="${1:-$(previous_version)}"
[[ -n "$TARGET" ]] || die "no previous release recorded; pass a version"
[[ "$TARGET" =~ ^[A-Za-z0-9._-]{1,128}$ ]] || die "bad version '$TARGET'"
exec 9>"$VSH_STATE_DIR/deploy.lock"
flock -n 9 || die "a deploy is running"
CURRENT="$(current_version)"
log "rolling back from ${CURRENT:-none} to $TARGET"
VSH_VERSION="$TARGET" dc pull --quiet backend frontend
VSH_VERSION="$TARGET" dc up -d --remove-orphans
VSH_VERSION="$TARGET" wait_ready 240 || die "$TARGET did not become ready"
if [[ -z "${SKIP_SMOKE:-}" ]]; then
  VSH_VERSION="$TARGET" run_smoke || die "smoke test failed on $TARGET"
fi
echo "$TARGET" >"$VSH_STATE_DIR/release/current"
[[ -n "$CURRENT" && "$CURRENT" != "$TARGET" ]] && echo "$CURRENT" >"$VSH_STATE_DIR/release/previous"
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) rollback to $TARGET (from ${CURRENT:-none})" >>"$VSH_STATE_DIR/release/history"
log "now running $TARGET"
