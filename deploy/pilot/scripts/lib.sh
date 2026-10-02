#!/usr/bin/env bash
# Shared helpers for the pilot scripts. Sourced, not executed.
#
# Layout on the VM (created by bootstrap-host.sh):
#   /opt/vanshavali                 this repository (deploy/pilot is used from here)
#   /etc/vanshavali/compose.env     non-secret settings: IMAGE_PREFIX, VSH_DOMAIN, VSH_TLS, replicas
#   /etc/vanshavali/app.env         backend/worker secrets (mode 600)
#   /etc/vanshavali/migrate.env     schema-owner database URL + app role password (mode 600)
#   /etc/vanshavali/backup.env      backup bucket + age recipient (mode 600)
#   /etc/vanshavali/smoke.env       smoke account (mode 600)
#   /var/lib/vanshavali/release     current / previous image versions
#   /var/lib/vanshavali/backups     local copies of recent encrypted dumps
#   /var/lib/vanshavali/textfile    node-exporter textfile metrics (backup status)
set -euo pipefail

VSH_CONFIG_DIR="${VSH_CONFIG_DIR:-/etc/vanshavali}"
VSH_STATE_DIR="${VSH_STATE_DIR:-/var/lib/vanshavali}"
DEPLOY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-$DEPLOY_DIR/compose.yml}"
export VSH_CONFIG_DIR

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
die() { log "ERROR: $*"; exit 1; }

# shellcheck disable=SC1091
load_env() { # load_env FILE: export every KEY=VALUE in FILE (no shell evaluation of values)
  local f="$1" line key
  [[ -r "$f" ]] || die "cannot read $f"
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
    key="${line%%=*}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || die "bad line in $f: $key"
    export "$key=${line#*=}"
  done <"$f"
}

check_secret_file() { # secrets must not be world/group readable
  local f="$1" mode
  [[ -f "$f" ]] || die "missing $f (see docs/deployment/environment-variables.md)"
  mode="$(stat -c %a "$f")"
  [[ "$mode" == 600 || "$mode" == 400 ]] || die "$f has mode $mode; run: chmod 600 $f"
}

current_version() { cat "$VSH_STATE_DIR/release/current" 2>/dev/null || true; }
previous_version() { cat "$VSH_STATE_DIR/release/previous" 2>/dev/null || true; }

dc() { # docker compose for the pilot stack; VSH_VERSION defaults to the deployed release
  VSH_VERSION="${VSH_VERSION:-$(current_version)}" \
    docker compose --env-file "$VSH_CONFIG_DIR/compose.env" -f "$COMPOSE_FILE" ${COMPOSE_OVERRIDE:+-f "$COMPOSE_OVERRIDE"} "$@"
}

image() { # image backend|frontend [version]
  load_env "$VSH_CONFIG_DIR/compose.env"
  printf '%s/vanshavali-%s:%s' "$IMAGE_PREFIX" "$1" "${2:-${VSH_VERSION:-$(current_version)}}"
}

wait_ready() { # wait_ready SECONDS: every backend replica answers readiness (DB, Redis, RLS in force)
  local deadline=$((SECONDS + ${1:-180})) n i
  n="$(dc ps -q backend | wc -l)"
  ((n > 0)) || return 1
  for ((i = 1; i <= n; i++)); do
    until dc exec -T --index "$i" backend python -c \
        "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/v1/health/ready', timeout=5)" \
        >/dev/null 2>&1; do
      ((SECONDS < deadline)) || return 1
      sleep 3
    done
  done
}

# shellcheck disable=SC2120 # arguments are optional pass-throughs
run_smoke() { # run_smoke [extra smoke args...]: the smoke test against the public name, through Caddy
  load_env "$VSH_CONFIG_DIR/compose.env"
  check_secret_file "$VSH_CONFIG_DIR/smoke.env"
  local ca_args=() user=()
  if [[ "${VSH_TLS}" == internal ]]; then # drills: trust Caddy's local CA (its files are root-only)
    ca_args=(--ca-file /caddy/caddy/pki/authorities/local/root.crt)
    user=(--user 0:0)
  fi
  # Inside the Compose network the public name resolves to Caddy, so TLS, routing and the proxy
  # chain are exercised exactly as for a user (DNS excepted).
  docker run --rm --network vanshavali_default --add-host "$VSH_DOMAIN:172.30.0.10" "${user[@]}" \
    --env-file "$VSH_CONFIG_DIR/smoke.env" -v vanshavali_caddy_data:/caddy:ro \
    "$(image backend)" python -m app.cli.smoke --base-url "https://$VSH_DOMAIN" "${ca_args[@]}" "$@"
}

pg_env_from_url() { # export PGHOST/PGPORT/PGUSER/PGPASSWORD/PGDATABASE/PGSSLMODE/PGSSLROOTCERT from a URL
  local url="$1" line
  while IFS= read -r line; do export "${line?}"; done < <(python3 - "$url" <<'PY'
import sys
from urllib.parse import parse_qs, unquote, urlsplit
u = urlsplit(sys.argv[1].replace("+psycopg", "", 1))
q = parse_qs(u.query)
print(f"PGHOST={u.hostname}")
print(f"PGPORT={u.port or 5432}")
print(f"PGUSER={unquote(u.username or '')}")
print(f"PGPASSWORD={unquote(u.password or '')}")
print(f"PGDATABASE={u.path.lstrip('/')}")
print(f"PGSSLMODE={q.get('sslmode', ['prefer'])[0]}")
if "sslrootcert" in q:
    print(f"PGSSLROOTCERT={q['sslrootcert'][0]}")
PY
  )
}

ensure_network() { # the stack network must exist before one-off containers join it (fresh VM, restore)
  docker network inspect vanshavali_default >/dev/null 2>&1 || dc up --no-start redis >/dev/null 2>&1
}

pg_tool() { # pg_tool CMD ARGS...: PostgreSQL 16 client tools from the official image, on the stack network
  ensure_network
  local certs=()
  [[ -n "${PGSSLROOTCERT:-}" ]] && certs=(-v "$PGSSLROOTCERT:$PGSSLROOTCERT:ro")
  docker run --rm -i --network vanshavali_default "${certs[@]}" \
    -e PGHOST -e PGPORT -e PGUSER -e PGPASSWORD -e PGDATABASE -e PGSSLMODE -e PGSSLROOTCERT \
    postgres:16-alpine "$@"
}

ops_backup() { # ops_backup ARGS...: app.cli.ops_backup with app + owner + backup settings; $1 dir mounted at /work
  local work="$1"; shift
  ensure_network
  docker run --rm --network vanshavali_default \
    --env-file "$VSH_CONFIG_DIR/app.env" --env-file "$VSH_CONFIG_DIR/migrate.env" \
    --env-file "$VSH_CONFIG_DIR/backup.env" -e VSH_ENV=development \
    -e PYTHONPATH=/app -v "$work:/work" -w /work --user "$(id -u):$(id -g)" "$(image backend)" \
    python -m app.cli.ops_backup "$@"
}
