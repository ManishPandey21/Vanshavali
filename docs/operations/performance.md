# Performance baseline (PRS §49)

Target: normal API p95 < 500 ms. Heavy search and analysis jobs are excluded. The target tree size
is 10,000+ people.

## Method
`backend/app/cli/benchmark.py` builds a synthetic multi-generation tree of fictional people:
2–4 children per couple and 25-year generations, with birth events, names and biological-parent
edges. It runs `ANALYZE` (as autovacuum would), then times each endpoint 20 times in-process via
the ASGI test client. That measures application and database time, not network time.

```bash
cd backend
createdb vsh_bench && VSH_DATABASE_URL=postgresql+psycopg://…/vsh_bench uv run alembic upgrade head
VSH_DATABASE_URL=…owner url… uv run python -m app.cli.benchmark --people 10000   # bulk load: needs the table owner (RLS)
```

## Results: 10,000 people, dev container (PostgreSQL 16 local), 25 Sep 2026

| Endpoint | p50 ms | p95 ms | Meets target |
|---|---|---|---|
| People list (page of 50, privacy-filtered) | 39 | 117 | ✓ |
| Person profile | 18 | 22 | ✓ |
| Family view | 23 | 27 | ✓ |
| Ancestors, depth 10 (recursive CTE) | 35 | 40 | ✓ |
| Descendants, depth 4 | 26 | 30 | ✓ |
| Search "krishna iyer" (transliteration, trigram, phonetic) | 66 | 133 | ✓ |
| Relationship path (whole-graph BFS + LCA) | 392 | 529 | ≈ (p95 slightly over) |
| Duplicate candidates (analysis job) | 2,891 | 2,998 | n/a (heavy job) |

## Fixes made while measuring
- **Relationship path, 1.9 s → 0.4 s:**
  - Privacy is evaluated only for people on the result, not the whole tree.
  - Edges load as lightweight tuples.
  - Sex is loaded only for touched people.
- **Duplicates, 100 s → 3 s:**
  - Candidates are compared only within a phonetic first/last name block plus the adjacent birth
    decade.
  - There is a hard budget of 250k pairs per request.
  - The synthetic data is a worst case: 10k people share just 200 name combinations.

## Next steps (Phase 8, measured triggers)
- **Relationship path:** the HTTP load test below shows it is *the* throughput and tail-latency
  bottleneck under concurrency. Fix it before go-live; the options are ranked below.
- **Duplicates:** move to a background job with cached results for trees over 20k people.
- **Tree size:** repeat with 100k people before choosing a graph projection (ADR-0002).

# HTTP load test (Phase 8)

## Method
`backend/app/cli/loadtest.py` (asyncio + httpx), orchestrated by `ops/loadtest/run.sh`:
1. `loadtest seed` builds the same synthetic tree as above (`benchmark.build`, 10,000 people,
   `ANALYZE`) plus N contributor accounts.
2. A real `uvicorn app.main:app --workers 4` serves it on 127.0.0.1. When the codebase has RLS, it
   runs as a non-owner app role.
3. `loadtest run`: each virtual user logs in with its own account (cookie session + CSRF header),
   then loops over a weighted mix with **zero think time**. The mix is 85% reads and 15% writes:

   | Operation | Weight |
   |---|---|
   | People list | 18 |
   | Profile | 20 |
   | Family | 15 |
   | Ancestors, depth 10 | 10 |
   | Descendants, depth 4 | 4 |
   | Name search | 10 |
   | Relationship path between two random people in the lower half of the tree | 8 |
   | Add person | 8 |
   | Add child via `/relatives` | 7 |

   5 s warm-up, then 60 s measured. Latency is client-side wall clock over loopback.
4. `run.sh` raises `VSH_LOGIN_RATE_LIMIT_PER_MINUTE` for the server under test only, because every
   virtual user logs in from 127.0.0.1.

```bash
ops/loadtest/run.sh                                   # 10k people, 20 and 50 users, 60 s each
PEOPLE=10000 USERS_LIST="20 50" DURATION=60 WORKERS=4 ops/loadtest/run.sh
cd backend && uv run python -m app.cli.loadtest run --users 20 --exclude "relationship path"  # what-if
```

**Read these numbers as a lower bound.** The test ran on a 4-vCPU dev container that also hosted
PostgreSQL, the load generator and other engineers' test suites (1-minute load average 8–20 during
the runs, recorded in each result JSON). A closed loop with no think time makes each virtual user a
saturating client, so 20 of them correspond to far more human users.

## Results: 10,000 people, uvicorn 4 workers, commit `06d0ced`, 25 Sep 2026
| Scenario | Throughput | Errors | p50 | p95 | p99 |
|---|---|---|---|---|---|
| 20 users, no think time | 31.8 req/s | 0 / 1,938 | 76 ms | 2,234 ms | 3,309 ms |
| 50 users, no think time | 36.1 req/s | 0 / 2,250 | 896 ms | 3,987 ms | 5,988 ms |
| 50 users, 2 s mean think time | 20.9 req/s | 0 / 1,322 | 93 ms | 1,160 ms | 2,318 ms |
| **What-if:** 20 users, relationship path removed from the mix | **94.5 req/s** | 0 / 4,290 | 194 ms | **492 ms** | 619 ms |
| Uncommitted RLS work, app role, 20 users | 40.6 req/s | 0 / 2,464 | 268 ms | 1,587 ms | 2,553 ms |
| Uncommitted RLS work, app role, 50 users | 32.4 req/s | 0 / 2,031 | 519 ms | 5,727 ms | 8,991 ms |

Per endpoint, 20 users, no think time (p50 / p95 / p99, ms):

| Endpoint | req/s | p50 | p95 | p99 |
|---|---|---|---|---|
| People list | 5.4 | 76 | 1,924 | 2,358 |
| Person profile | 6.4 | 37 | 1,767 | 2,137 |
| Family view | 4.8 | 44 | 2,018 | 2,276 |
| Ancestors, depth 10 | 3.1 | 75 | 2,054 | 2,351 |
| Descendants, depth 4 | 1.1 | 60 | 2,016 | 2,393 |
| Search | 3.4 | 102 | 1,906 | 2,563 |
| **Relationship path** | 2.8 | **765** | **3,547** | 4,063 |
| Add person | 2.6 | 45 | 2,049 | 2,641 |
| Add relative | 2.2 | 79 | 2,634 | 3,323 |

Per endpoint, 50 users, no think time: every endpoint has p50 586–1,345 ms and p95 2.9–5.2 s.
Relationship path has p50 2,698 ms and p95 5,860 ms. The error rate is 0% in every run: no 5xx,
no timeouts, no pool exhaustion.

The two RLS rows are within the noise of the committed-code runs. On this box the RLS cost cannot
be separated from host contention; re-measure on a quiet machine.

## Bottlenecks found
1. **Relationship path saturates the CPU and causes head-of-line blocking.**
   - `py-spy` on the four workers under the 20-user mix shows that it takes **45% of all worker
     CPU samples** for 8% of requests. `_load_graph` alone is 36%: every call loads all ~20k
     `relationship` rows of the tree and builds adjacency dicts in Python. Most of that is
     psycopg/SQLAlchemy row decoding, not database time.
   - Because this work is CPU-bound Python holding the GIL, a worker busy with one path request
     stalls the other requests on its thread pool. That is why cheap endpoints show p50 ≈ 40–100 ms
     but p95 ≈ 2 s: the distribution is bimodal.
   - Removing it from the mix triples throughput (31.8 → 94.5 req/s) and brings the overall p95
     under the 500 ms target at 20 saturating users.
2. **After that, Python CPU per request.** Session and authz loading, privacy evaluation (~14%
   of samples) and serialisation (~13%) sit on a 4-core box shared with PostgreSQL.
   - Captured per request, individual SQL statements are fast: the trigram name search is about
     32 ms, and the rest (people-list page, birth-event lookup, session, membership) are under
     10 ms.
   - Throughput scales with cores and workers, not with database tuning.
3. **Indexes: no clear win.**
   - I tried a partial index `person (tree_id, preferred_display_name, id) WHERE deleted_at IS NULL`
     on the load-test database only, never by migration. It turned the people-list query from a
     seq scan + top-N sort into an index scan: 3.9 → 0.2 ms for page 1, 15 → 6 ms at offset 5,000.
   - It made **no measurable HTTP difference**: people-list-only run, 4 users, 33.3 vs 34.0 req/s.
   - So no migration is proposed now. It becomes worth adding when trees reach 100k+ people or
     deep pagination matters. Suggested DDL for the lead, if wanted:
     `CREATE INDEX ix_person_tree_display_name ON person (tree_id, preferred_display_name, id) WHERE deleted_at IS NULL`.

## Recommendations (ranked)
1. **Relationship path:** stop loading the whole edge set per request. The options, in order of
   preference:
   - (a) bidirectional BFS that fetches neighbours per frontier with indexed queries (touches
     hundreds of rows, not 20k);
   - (b) two recursive-CTE ancestor sets and an LCA in SQL for blood relations (the ancestors
     endpoint already does depth 10 in ~35 ms), with BFS only as a fallback for in-law paths;
   - (c) a per-tree adjacency cache keyed by a relationship-change version.

   Until one lands, cap concurrent path computations per worker (a semaphore of 1–2) so they queue
   instead of starving other requests. Re-run `loadtest --exclude` to measure.
2. **Capacity:** on this hardware, one 4-vCPU backend node sustains about 30–35 req/s of this mix
   (about 95 req/s without relationship path). At an assumed 1 request per 5 s per active human
   user, that is about 150 concurrent active users per node today (**ASSUMPTION** about usage).
   Scale horizontally with workers = vCPUs, and keep PostgreSQL on its own host.
3. Re-run on a dedicated host, with the RLS app role, and at 100k people before choosing a graph
   projection (ADR-0002).

