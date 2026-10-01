#!/usr/bin/env bash
# Performance certification (PRS §49: normal API p95 < 500 ms at 10,000 people).
# See docs/operations/performance.md ("Certification protocol") for how to read the results.
#
# Three measurements, in this order, against a real uvicorn server running as the RLS app role:
#   1. sequential  - one user, one request at a time: the latency a person sees on an idle server
#   2. sweep       - open-loop (Poisson) arrivals at fixed rates: p50/p95/p99 and errors at each
#                    sustained rate, and the highest rate that still meets the p95 target (capacity)
#   3. stress      - closed loop, zero think time (saturation; diagnostic only, not the SLO)
#
# Usage, from the repo root on the host under test (needs PostgreSQL superuser access, uv, openssl):
#   ops/loadtest/certify.sh
#   PEOPLE=10000 WORKERS=4 RATES="5,10,20,30,40,60" DURATION=60 ops/loadtest/certify.sh
# Two hosts (recommended: the generator must not share the server's CPUs):
#   server host:    SERVE_ONLY=1 ops/loadtest/certify.sh   # seed, then serve on 0.0.0.0:$PORT until Ctrl-C
#   generator host: copy <OUT>/state.json, then run `loadtest sequential` / `loadtest sweep` against it
#                   (docs/operations/performance.md, "Running it on a dedicated staging host")
#
# Env: PGHOST/PGUSER/PGPASSWORD (default localhost/vanshavali/vanshavali), CERT_DB (vsh_cert),
#      PORT (8300), OUT (ops/loadtest/results/cert-<timestamp>), SKIP_STRESS=1 to skip step 3.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PGHOST="${PGHOST:-localhost}" PGUSER="${PGUSER:-vanshavali}" PGPASSWORD="${PGPASSWORD:-vanshavali}"
CERT_DB="${CERT_DB:-vsh_cert}"
PEOPLE="${PEOPLE:-10000}"
WORKERS="${WORKERS:-$(nproc)}"
RATES="${RATES:-5,10,20,30,40,60}"
DURATION="${DURATION:-60}"
SESSIONS="${SESSIONS:-40}"
PORT="${PORT:-8300}"
OUT="${OUT:-$ROOT/ops/loadtest/results/cert-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT"
cd "$ROOT/backend"

{
  echo "git: $(git -C "$ROOT" rev-parse --short HEAD) $(git -C "$ROOT" status --porcelain | grep -q . && echo '(dirty)')"
  echo "host: $(uname -srm), $(nproc) vCPU, $(free -g | awk '/Mem:/{print $2}') GiB RAM"
  echo "postgres: $(psql -d postgres -tAc 'show server_version')"
  echo "people=$PEOPLE workers=$WORKERS rates=$RATES duration=${DURATION}s sessions=$SESSIONS"
  echo "loadavg before: $(cut -d' ' -f1-3 /proc/loadavg)"
} | tee "$OUT/environment.txt"

export VSH_DATABASE_URL="postgresql+psycopg://$PGUSER:$PGPASSWORD@$PGHOST:5432/$CERT_DB"
export VSH_JOB_MODE=sync VSH_STORAGE_LOCAL_PATH="$OUT/storage" VSH_LOG_LEVEL=WARNING
# synthetic sessions all log in from one address in the same second: lift only the login throttle
export VSH_LOGIN_RATE_LIMIT_PER_MINUTE=100000

echo "== fresh database $CERT_DB, migrations, $PEOPLE-person tree"
dropdb --if-exists "$CERT_DB"
createdb "$CERT_DB"
uv run alembic upgrade head >/dev/null
uv run python -m app.cli.loadtest seed --people "$PEOPLE" --users "$SESSIONS" --state "$OUT/state.json"

if [[ -z "${BASE_URL:-}" ]]; then
  APP_ROLE=vsh_cert_app
  APP_PW="$(openssl rand -hex 16)"
  VSH_APP_DB_ROLE="$APP_ROLE" VSH_APP_DB_PASSWORD="$APP_PW" uv run python -m app.cli.ensure_app_role
  BIND=127.0.0.1
  [[ -n "${SERVE_ONLY:-}" ]] && BIND=0.0.0.0
  echo "== uvicorn --workers $WORKERS on $BIND:$PORT as $APP_ROLE (row-level security applies)"
  VSH_DATABASE_URL="postgresql+psycopg://$APP_ROLE:$APP_PW@$PGHOST:5432/$CERT_DB" \
    uv run uvicorn app.main:app --host "$BIND" --port "$PORT" --workers "$WORKERS" --no-access-log \
    >"$OUT/server.log" 2>&1 &
  SERVER=$!
  trap 'kill $SERVER 2>/dev/null || true; wait $SERVER 2>/dev/null || true' EXIT
  BASE_URL="http://127.0.0.1:$PORT"
  for _ in $(seq 120); do curl -fsS "$BASE_URL/api/v1/health/ready" >/dev/null 2>&1 && break; sleep 0.5; done
  curl -fsS "$BASE_URL/api/v1/health/ready" | tee "$OUT/ready.json"; echo
  if [[ -n "${SERVE_ONLY:-}" ]]; then
    echo "serving on 0.0.0.0:$PORT; copy $OUT/state.json to the generator host. Ctrl-C to stop."
    wait "$SERVER"
    exit 0
  fi
fi

LT=(uv run python -m app.cli.loadtest)
status=0 # every step runs; a step with > 1% errors marks the whole certification as failed
echo "== 1/3 sequential"
"${LT[@]}" sequential --base-url "$BASE_URL" --state "$OUT/state.json" --per-endpoint 50 \
  --json "$OUT/sequential.json" | tee "$OUT/sequential.txt" || status=1
echo "== 2/3 open-loop sweep: $RATES req/s"
"${LT[@]}" sweep --base-url "$BASE_URL" --state "$OUT/state.json" --rates "$RATES" --users "$SESSIONS" \
  --duration "$DURATION" --json "$OUT/sweep.json" | tee "$OUT/sweep.txt" || status=1
if [[ -z "${SKIP_STRESS:-}" ]]; then
  echo "== 3/3 closed-loop stress, 20 users, zero think time (diagnostic, does not affect the status)"
  "${LT[@]}" run --base-url "$BASE_URL" --state "$OUT/state.json" --users 20 --duration "$DURATION" \
    --json "$OUT/stress-20.json" | tee "$OUT/stress-20.txt" || true
fi
echo "loadavg after: $(cut -d' ' -f1-3 /proc/loadavg)" | tee -a "$OUT/environment.txt"
echo "results: $OUT (status $status)"
exit "$status"
