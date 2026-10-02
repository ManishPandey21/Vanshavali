#!/usr/bin/env bash
# Reproducible staging drill of the pilot stack (docs/operations/backup-restore-runbook.md, "Drill").
#
#   VSH_VERSION=<image tag> IMAGE_PREFIX=<registry/owner> deploy/pilot/drill/run-drill.sh
#
# Runs the real compose.yml, Caddyfile and scripts, with stand-ins for the managed services
# (compose.drill.yml). Phases, each timed into $DRILL_DIR/drill-report.json:
#   A. deploy: generate config + keys + certs, start the stand-ins, deploy.sh (migrate, roll, ready)
#   B. email: register the smoke account through the API; the verification email goes worker ->
#      SMTP (STARTTLS) -> sink; the drill follows the link
#   C. smoke: full 13-step smoke test, keeping its tree ("Restore drill"); a synthetic tree of
#      DRILL_PEOPLE people for realistic size
#   D. backup: backup.sh (encrypted dump + manifest + object mirror to the backup bucket)
#   E. writes after the backup ("After backup" tree) -> must be lost: proves the RPO boundary
#   F. disaster: stop the stack, destroy the database volume, the primary bucket and Redis
#   G. restore into the clean environment: restore.sh --objects, deploy.sh, smoke --verify-existing,
#      then a full smoke test (the restored site accepts new writes)
# Needs: docker with compose v2, age, openssl, python3, curl; uv for seeding (DRILL_PEOPLE=0 skips).
# Options (env): DRILL_DIR (default: a new temp dir), DRILL_PEOPLE (10000), KEEP=1 (leave it running),
# SKIP_PULL=1 (images built locally), DRILL_NO_OCR=1 (image without tesseract).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
: "${VSH_VERSION:?set VSH_VERSION to the image tag}" "${IMAGE_PREFIX:?set IMAGE_PREFIX}"
export DRILL_DIR="${DRILL_DIR:-$(mktemp -d /tmp/vsh-drill.XXXXXX)}"
export VSH_CONFIG_DIR="$DRILL_DIR/config" VSH_STATE_DIR="$DRILL_DIR/state"
export COMPOSE_OVERRIDE="$ROOT/deploy/pilot/drill/compose.drill.yml"
DRILL_PEOPLE="${DRILL_PEOPLE:-10000}"
# shellcheck source=deploy/pilot/scripts/lib.sh
source "$ROOT/deploy/pilot/scripts/lib.sh"

declare -A T
now() { date +%s%3N; }
mark() { T[$1]=$(($(now) - $2)); log "phase $1: ${T[$1]} ms"; }
rnd() { openssl rand -hex "${1:-24}"; }
b64key() { openssl rand -base64 32; }
in_net() { # run a python snippet on the stack network with the public name resolving to Caddy
  docker run --rm -i --network vanshavali_default --add-host pilot.test:172.30.0.10 \
    -v vanshavali_caddy_data:/caddy:ro --user 0:0 -e SSL_CERT_FILE=/caddy/caddy/pki/authorities/local/root.crt \
    "$(image backend)" python - "$@"
}

# ------------------------------------------------------------------ A. configuration and deploy
t0=$(now)
mkdir -p "$VSH_CONFIG_DIR" "$VSH_STATE_DIR/release" "$VSH_STATE_DIR/backups" "$VSH_STATE_DIR/textfile" "$DRILL_DIR/mail"
chmod 700 "$VSH_CONFIG_DIR"
chmod 777 "$DRILL_DIR/mail" # the sink container writes here
cp "$ROOT/deploy/pilot/drill/smtp_sink.py" "$DRILL_DIR/"
age-keygen -o "$DRILL_DIR/age-key.txt" 2>/dev/null
AGE_RECIPIENT="$(age-keygen -y "$DRILL_DIR/age-key.txt")"
openssl req -x509 -newkey rsa:2048 -nodes -days 2 -subj "/CN=Vanshavali drill CA" \
  -keyout "$DRILL_DIR/ca.key" -out "$DRILL_DIR/ca.crt" 2>/dev/null
openssl req -newkey rsa:2048 -nodes -subj "/CN=smtp" -keyout "$DRILL_DIR/smtp.key" -out "$DRILL_DIR/smtp.csr" 2>/dev/null
openssl x509 -req -in "$DRILL_DIR/smtp.csr" -CA "$DRILL_DIR/ca.crt" -CAkey "$DRILL_DIR/ca.key" -CAcreateserial \
  -days 2 -extfile <(printf 'subjectAltName=DNS:smtp') -out "$DRILL_DIR/smtp.crt" 2>/dev/null
chmod 644 "$DRILL_DIR/smtp.key" "$DRILL_DIR/ca.crt" "$DRILL_DIR/smtp.crt"
OWNER_PW="$(rnd)" APP_PW="$(rnd)" S3_KEY="drill$(rnd 8)" S3_SECRET="$(rnd)"
DRILL_PG_ADMIN_PASSWORD="$(rnd)"
export DRILL_PG_ADMIN_PASSWORD
cat >"$DRILL_DIR/pg-init.sql" <<SQL
CREATE ROLE vanshavali_owner LOGIN CREATEROLE PASSWORD '$OWNER_PW';
CREATE DATABASE vanshavali OWNER vanshavali_owner;
SQL
cat >"$VSH_CONFIG_DIR/compose.env" <<EOF
IMAGE_PREFIX=$IMAGE_PREFIX
VSH_DOMAIN=pilot.test
VSH_TLS=internal
BACKEND_REPLICAS=2
WORKER_REPLICAS=2
EOF
cat >"$VSH_CONFIG_DIR/app.env" <<EOF
VSH_DATABASE_URL=postgresql+psycopg://vanshavali_app:$APP_PW@pgmanaged:5432/vanshavali
VSH_S3_ENDPOINT_URL=http://s3:5000
VSH_S3_REGION=ap-south-1
VSH_S3_BUCKET=vanshavali-drill-documents
VSH_S3_ACCESS_KEY=$S3_KEY
VSH_S3_SECRET_KEY=$S3_SECRET
VSH_STANDARD_DATA_KEY=$(b64key)
VSH_VAULT_DATA_KEY=$(b64key)
VSH_SIGNING_KEY=$(rnd 32)
VSH_SMTP_HOST=smtp
VSH_SMTP_PORT=587
VSH_SMTP_USER=drill
VSH_SMTP_PASSWORD=$(rnd)
VSH_MAIL_FROM=Vanshavali <no-reply@pilot.test>
VSH_METRICS_TOKEN=$(rnd)
VSH_LOGIN_RATE_LIMIT_PER_MINUTE=100
${DRILL_NO_OCR:+VSH_OCR_ENABLED=false}
EOF
cat >"$VSH_CONFIG_DIR/migrate.env" <<EOF
VSH_DATABASE_URL=postgresql+psycopg://vanshavali_owner:$OWNER_PW@pgmanaged:5432/vanshavali
VSH_APP_DB_ROLE=vanshavali_app
VSH_APP_DB_PASSWORD=$APP_PW
EOF
cat >"$VSH_CONFIG_DIR/backup.env" <<EOF
BACKUP_AGE_RECIPIENT=$AGE_RECIPIENT
BACKUP_S3_ENDPOINT_URL=http://s3:5000
BACKUP_S3_REGION=ap-south-1
BACKUP_S3_BUCKET=vanshavali-drill-backups
BACKUP_S3_ACCESS_KEY=$S3_KEY
BACKUP_S3_SECRET_KEY=$S3_SECRET
EOF
SMOKE_PW="Smoke-$(rnd 12)"
printf 'SMOKE_EMAIL=smoke@drill.example.org\nSMOKE_PASSWORD=%s\n' "$SMOKE_PW" >"$VSH_CONFIG_DIR/smoke.env"
chmod 600 "$VSH_CONFIG_DIR"/*.env

buckets() { # buckets create|wipe-primary
  docker run --rm -i --network vanshavali_default -e AWS_ACCESS_KEY_ID="$S3_KEY" -e AWS_SECRET_ACCESS_KEY="$S3_SECRET" \
    "${DRILL_TOOLS_IMAGE:-vsh-drill-tools:local}" python - "$1" <<'PY'
import sys, boto3
s3 = boto3.client("s3", endpoint_url="http://s3:5000", region_name="ap-south-1")
primary, backup = "vanshavali-drill-documents", "vanshavali-drill-backups"
if sys.argv[1] == "create":
    for b in (primary, backup):
        s3.create_bucket(Bucket=b, CreateBucketConfiguration={"LocationConstraint": "ap-south-1"})
        s3.put_bucket_versioning(Bucket=b, VersioningConfiguration={"Status": "Enabled"})
    print("buckets created (versioning on)")
else:  # total loss of the primary bucket: every version, then the bucket itself; recreate empty
    n = 0
    for page in s3.get_paginator("list_object_versions").paginate(Bucket=primary):
        for v in page.get("Versions", []) + page.get("DeleteMarkers", []):
            s3.delete_object(Bucket=primary, Key=v["Key"], VersionId=v["VersionId"]); n += 1
    s3.delete_bucket(Bucket=primary)
    s3.create_bucket(Bucket=primary, CreateBucketConfiguration={"LocationConstraint": "ap-south-1"})
    s3.put_bucket_versioning(Bucket=primary, VersioningConfiguration={"Status": "Enabled"})
    print(f"primary bucket destroyed ({n} object versions) and recreated empty")
PY
}

log "drill dir: $DRILL_DIR"
dc up -d --wait pgmanaged s3 smtp
buckets create
SKIP_SMOKE=1 "$ROOT/deploy/pilot/scripts/deploy.sh" "$VSH_VERSION"
mark A_deploy "$t0"

# ------------------------------------------------------------------ B. email round trip
t0=$(now)
in_net "$SMOKE_PW" <<'PY'
import json, ssl, sys, urllib.request
pw = sys.argv[1]
req = urllib.request.Request("https://pilot.test/api/v1/auth/register", method="POST",
    data=json.dumps({"email": "smoke@drill.example.org", "password": pw, "display_name": "Smoke Test"}).encode(),
    headers={"Content-Type": "application/json"})
print("register:", urllib.request.urlopen(req, timeout=30).status)
PY
deadline=$((SECONDS + 120))
until ls "$DRILL_DIR"/mail/*.eml >/dev/null 2>&1; do ((SECONDS < deadline)) || die "no verification email in 120 s"; sleep 2; done
TOKEN="$(python3 - "$DRILL_DIR"/mail/*.eml <<'PY'
import email, email.policy, re, sys
for path in sys.argv[1:]:
    msg = email.message_from_bytes(open(path, "rb").read(), policy=email.policy.default)
    body = msg.get_body(("plain",)).get_content()
    m = re.search(r"/verify-email/([A-Za-z0-9_-]{32,})", body)
    if m:
        print(m.group(1)); break
PY
)"
[[ -n "$TOKEN" ]] || die "verification link not found in the email"
grep -q "^Message-ID:" "$DRILL_DIR"/mail/*.eml || die "email without Message-ID"
in_net "$TOKEN" <<'PY'
import json, sys, urllib.request
req = urllib.request.Request("https://pilot.test/api/v1/auth/verify-email", method="POST",
    data=json.dumps({"token": sys.argv[1]}).encode(), headers={"Content-Type": "application/json"})
print("verify-email:", urllib.request.urlopen(req, timeout=30).status)
PY
mark B_email "$t0"

# ------------------------------------------------------------------ C. smoke + realistic data
t0=$(now)
run_smoke --keep --tree-name "Restore drill"
if ((DRILL_PEOPLE > 0)); then
  (cd "$ROOT/backend" && VSH_DATABASE_URL="$(grep '^VSH_DATABASE_URL=' "$VSH_CONFIG_DIR/migrate.env" | cut -d= -f2- | sed "s/@pgmanaged:5432/@127.0.0.1:${DRILL_PG_PORT:-55432}/")" \
    uv run python -c "from app.cli.benchmark import build; t, *_ = build($DRILL_PEOPLE); print('synthetic tree', t)")
fi
mark C_seed "$t0"

# ------------------------------------------------------------------ D. backup
t0=$(now)
BACKUP="$("$ROOT/deploy/pilot/scripts/backup.sh" drill | tail -1)"
mark D_backup "$t0"
cat "$VSH_STATE_DIR/textfile/vsh_backup.prom" >"$DRILL_DIR/backup-metrics.prom"

# ------------------------------------------------------------------ E. writes after the backup
run_smoke --keep --tree-name "After backup" >/dev/null
BACKUP_AT_EPOCH="$(date -d "$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["taken_at_utc"])' \
  "$VSH_STATE_DIR/backups/$BACKUP/manifest.json")" +%s)"

# ------------------------------------------------------------------ F. disaster
DISASTER_EPOCH=$(date +%s)
t_disaster=$(now)
# Everything the pilot VM and the managed database hold is destroyed. The backup store (s3 stand-in,
# in-memory, playing the separate backup bucket/account) and the mail sink stay up, as they would.
dc rm -sfv backend worker frontend caddy redis clamav pgmanaged >/dev/null
docker volume rm vanshavali_pgmanaged vanshavali_redis_data >/dev/null
dc up -d --wait pgmanaged
buckets wipe-primary
mark F_destroy "$t_disaster"

# ------------------------------------------------------------------ G. restore and verify
t0=$(now)
"$ROOT/deploy/pilot/scripts/restore.sh" "$BACKUP" --identity "$DRILL_DIR/age-key.txt" --objects
mark G1_restore_data "$t0"
t0=$(now)
SKIP_BACKUP=1 SKIP_SMOKE=1 "$ROOT/deploy/pilot/scripts/deploy.sh" "$VSH_VERSION"
mark G2_start_stack "$t0"
t0=$(now)
run_smoke --verify-existing "Restore drill"
mark G3_verify "$t0"
RTO_MS=$(($(now) - t_disaster))
lost="$(in_net "$SMOKE_PW" <<'PY'
import http.cookiejar, json, sys, urllib.request
jar = http.cookiejar.CookieJar()
op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
op.open("https://pilot.test/api/v1/auth/providers", timeout=30)
csrf = next(c.value for c in jar if c.name == "vsh_csrf")
op.open(urllib.request.Request("https://pilot.test/api/v1/auth/login", method="POST",
    data=json.dumps({"email": "smoke@drill.example.org", "password": sys.argv[1]}).encode(),
    headers={"Content-Type": "application/json", "X-CSRF-Token": csrf}), timeout=30)
names = [t["name"] for t in json.load(op.open("https://pilot.test/api/v1/trees", timeout=30))]
print("absent" if "After backup" not in names else "present")
PY
)"
[[ "$lost" == absent ]] || die "the tree written after the backup survived: the restore did not come from the backup"
t0=$(now)
run_smoke --tree-name "Post-restore write"
mark G4_post_restore_smoke "$t0"

python3 - "$DRILL_DIR/drill-report.json" "$VSH_STATE_DIR/last-restore.json" <<PY
import json, sys
phases = {$(for k in "${!T[@]}"; do printf '"%s": %s, ' "$k" "${T[$k]}"; done)}
report = {
    "version": "$VSH_VERSION", "people": $DRILL_PEOPLE, "backup": "$BACKUP",
    "phases_ms": dict(sorted(phases.items())),
    "rpo_boundary_s": $DISASTER_EPOCH - $BACKUP_AT_EPOCH,
    "rto_ms_disaster_to_verified": $RTO_MS,
    "writes_after_backup": "$lost (expected absent)",
    "restore": json.load(open(sys.argv[2])),
}
json.dump(report, open(sys.argv[1], "w"), indent=1)
print(json.dumps(report, indent=1))
PY
if [[ -z "${KEEP:-}" ]]; then
  dc down -v --remove-orphans >/dev/null 2>&1 || true
fi
log "drill passed; report: $DRILL_DIR/drill-report.json"
