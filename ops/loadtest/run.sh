#!/usr/bin/env bash
# HTTP load test: fresh database -> migrate -> seed 10k-person tree -> uvicorn (N workers) -> runs.
#
# Usage (from repo root; needs a local PostgreSQL superuser and uv):
#   ops/loadtest/run.sh                      # 10k people, 20 and 50 users, 60 s each
#   PEOPLE=10000 USERS_LIST="20 50" DURATION=60 WORKERS=4 ops/loadtest/run.sh
#
# Env: PGHOST/PGUSER/PGPASSWORD (default localhost/vanshavali/vanshavali), LT_DB (vsh_loadtest),
#      PORT (8200), OUT (ops/loadtest/results). Results: $OUT/users-<n>.json and the server log.
# When the codebase has app/cli/ensure_app_role.py (RLS, ADR-0002) the server runs as a non-owner
# role (LT_APP_ROLE, default vsh_loadtest_app) so row-level security cost is included; seeding
# uses the owner connection. The database is dropped and recreated each run. The login rate limit is raised for the server
# under test only (every virtual user logs in from 127.0.0.1 within the same second).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export PGHOST="${PGHOST:-localhost}" PGUSER="${PGUSER:-vanshavali}" PGPASSWORD="${PGPASSWORD:-vanshavali}"
LT_DB="${LT_DB:-vsh_loadtest}"
PEOPLE="${PEOPLE:-10000}"
USERS_LIST="${USERS_LIST:-20 50}"
DURATION="${DURATION:-60}"
WORKERS="${WORKERS:-4}"
PORT="${PORT:-8200}"
OUT="${OUT:-$ROOT/ops/loadtest/results}"
mkdir -p "$OUT"
MAX_USERS=$(tr ' ' '\n' <<<"$USERS_LIST" | sort -n | tail -1)

export VSH_DATABASE_URL="postgresql+psycopg://$PGUSER:$PGPASSWORD@$PGHOST:5432/$LT_DB"
export VSH_JOB_MODE=sync VSH_LOGIN_RATE_LIMIT_PER_MINUTE=100000
export VSH_STORAGE_LOCAL_PATH="$OUT/storage"

cd "$ROOT/backend"
echo "== database $LT_DB"
dropdb --if-exists "$LT_DB"
createdb "$LT_DB"
uv run alembic upgrade head >/dev/null
echo "== seed $PEOPLE people, $MAX_USERS users"
uv run python -m app.cli.loadtest seed --people "$PEOPLE" --users "$MAX_USERS" --state "$OUT/state.json"

SERVER_URL="$VSH_DATABASE_URL"
if [[ -f app/cli/ensure_app_role.py ]]; then
  LT_APP_ROLE="${LT_APP_ROLE:-vsh_loadtest_app}"
  LT_APP_PW="$(openssl rand -hex 16)"
  VSH_APP_DB_ROLE="$LT_APP_ROLE" VSH_APP_DB_PASSWORD="$LT_APP_PW" uv run python -m app.cli.ensure_app_role
  SERVER_URL="postgresql+psycopg://$LT_APP_ROLE:$LT_APP_PW@$PGHOST:5432/$LT_DB"
fi

echo "== uvicorn --workers $WORKERS on :$PORT"
VSH_DATABASE_URL="$SERVER_URL" uv run uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --workers "$WORKERS" --no-access-log \
  >"$OUT/server.log" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null || true; wait $SERVER 2>/dev/null || true' EXIT
for _ in $(seq 60); do curl -fsS "http://127.0.0.1:$PORT/api/v1/health" >/dev/null 2>&1 && break; sleep 0.5; done

status=0
for n in $USERS_LIST; do
  uv run python -m app.cli.loadtest run --base-url "http://127.0.0.1:$PORT" --state "$OUT/state.json" \
    --users "$n" --duration "$DURATION" --json "$OUT/users-$n.json" || status=1
done
exit $status
