#!/usr/bin/env bash
set -euo pipefail
cd /home/user/Vanshavali/backend
OUT=/tmp/claude-0/perf
OWNER_URL="$(grep '^VSH_DATABASE_URL=' /tmp/claude-0/drill2/config/migrate.env | cut -d= -f2- | sed 's/@pgmanaged:5432/@127.0.0.1:55432/')"
unset HTTPS_PROXY https_proxy HTTP_PROXY http_proxy
export SSL_CERT_FILE=/tmp/claude-0/caddy-root.crt NO_PROXY='*'
echo "== seed $(date -u +%T)"
VSH_DATABASE_URL="$OWNER_URL" uv run python -m app.cli.loadtest seed --people 10000 --users 40 --state $OUT/state.json 2>&1 | grep -v Deprecation | tail -3
# resource sampler: per-container CPU/mem every 5 s, DB counters every 5 s
( while true; do
    echo "## $(date -u +%T)"; docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}' | grep vanshavali-
    docker exec vanshavali-pgmanaged-1 psql -U admin -d vanshavali -XAtc "select 'db', numbackends, xact_commit, blks_hit, blks_read, tup_returned from pg_stat_database where datname='vanshavali'"
    sleep 5
  done ) > $OUT/resources.log 2>&1 &
SAMPLER=$!
trap 'kill $SAMPLER' EXIT
B="https://pilot.test"
echo "== sequential $(date -u +%T)"
uv run python -m app.cli.loadtest sequential --base-url $B --state $OUT/state.json --per-endpoint 50 --json $OUT/sequential.json 2>&1 | grep -v Deprecation | tail -20
for run in 1 2 3; do
  echo "== sweep run $run $(date -u +%T)"
  uv run python -m app.cli.loadtest sweep --base-url $B --state $OUT/state.json --rates 10,20,30,40,50 --users 40 --duration 40 --json $OUT/sweep-$run.json 2>&1 | grep -v Deprecation | tail -12
done
echo "== overload $(date -u +%T)"
uv run python -m app.cli.loadtest sweep --base-url $B --state $OUT/state.json --rates 70 --users 40 --duration 40 --json $OUT/overload.json 2>&1 | grep -v Deprecation | tail -8
echo "== done $(date -u +%T)"
