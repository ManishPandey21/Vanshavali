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
- **Relationship path: fixed (recommendation 1a below).** The load test showed it was *the*
  throughput and tail-latency bottleneck. Results are in "After the relationship-path fix" below.
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

## After the relationship-path fix (Phase 8)
What changed:
- The calculator no longer loads the tree's edge list per call (`engine._LazyGraph`). It fetches
  edges with one indexed query per BFS frontier.
- Blood-relation paths are built from the two upward ancestor searches, with no downward search.
- The in-law and marriage fallback is a bidirectional BFS that expands the smaller frontier.
- `tests/test_relationship_search.py` checks it against plain BFS on 300 random graphs.
- `test_genealogy.py::test_relationship_path_loads_only_the_neighbourhood` checks that unrelated
  families are never loaded.

Relationship path, same 10k synthetic tree, in-process, single client:

| Pair | Before | After (p50 / p95) |
|---|---|---|
| leaf → mid (14th cousin once removed) | 1,869 / 2,043 ms | **71 / 149 ms** |
| leaf → root (17× great-grandfather) | n/a | 47 / 54 ms |
| 40 random pairs from the load-test mix (lower half of the tree) | n/a | **85 / 137 ms** |

HTTP load test, 20 users, RLS app role, same shared 4-vCPU box:

| Run | Throughput | Overall p95 | Relationship path p50 / p95 |
|---|---|---|---|
| Before (RLS working tree) | 40.6 req/s | 1,587 ms | n/a |
| After | **75.4 req/s** | **764 ms** | 318 / 1,394 ms |

The "after" run was taken with a load average of 9–21 from other test suites on the same 4 vCPUs.
Overall p95 is still above the 500 ms target in a closed loop with no think time. The remaining
tail is CPU queueing on the shared box, not a single dominant endpoint: every route sits at a
similar p95. Re-measure on a dedicated host before sizing.

## Recommendations (ranked)
1. **Relationship path: done (1a).** Original analysis: stop loading the whole edge set per request. The options, in order of
   preference:
   - (a) bidirectional BFS that fetches neighbours per frontier with indexed queries (touches
     hundreds of rows, not 20k);
   - (b) two recursive-CTE ancestor sets and an LCA in SQL for blood relations (the ancestors
     endpoint already does depth 10 in ~35 ms), with BFS only as a fallback for in-law paths;
   - (c) a per-tree adjacency cache keyed by a relationship-change version.

   Option (a) is implemented. (b) and (c) remain available if 100k-person trees need them.
2. **Capacity:** on this hardware, one 4-vCPU backend node sustains about 30–35 req/s of this mix
   (about 95 req/s without relationship path). At an assumed 1 request per 5 s per active human
   user, that is about 150 concurrent active users per node today (**ASSUMPTION** about usage).
   Scale horizontally with workers = vCPUs, and keep PostgreSQL on its own host.
3. Re-run on a dedicated host, with the RLS app role, and at 100k people before choosing a graph
   projection (ADR-0002).


# Production-readiness certification (October 2026)

## Why the earlier load test cannot certify the target
PRS §49 asks for a **normal** API p95 under 500 ms. The Phase 8 HTTP test ran a closed loop with
zero think time: every virtual user sends its next request the instant the last one returns. That
measures a saturated server, where p95 is mostly queueing. It is useful for finding bottlenecks, but
it is not the latency of normal use. Its latency also suffers from coordinated omission: a slow
response delays the next request, so the slowest periods are under-sampled.

## Certification protocol (`ops/loadtest/certify.sh`)
Each run uses a fresh database, the migrations, a 10,000-person synthetic tree, and a server running
as the RLS-restricted app role. It records the host, CPU count, PostgreSQL version and git commit
next to the results. Three measurements:

| Step | Command | What it answers |
|---|---|---|
| 1. Sequential | `loadtest sequential` (1 user, 50 timed calls per operation after 3 warm-ups) | The latency a person sees on an idle server. |
| 2. Open-loop sweep | `loadtest sweep --rates …` | p50/p95/p99 and errors at each **sustained** arrival rate (Poisson). Latency is measured from each request's *scheduled* time, so there is no coordinated omission. The sessions log in once before the first rate, because Argon2id logins are deliberately CPU-heavy (~83 ms on 4 threads each). Capacity is the highest rate with p95 ≤ 500 ms and < 1% errors. |
| 3. Stress (diagnostic) | `loadtest run` (closed loop, 20 users) | Saturation behaviour only; not part of the pass/fail. |

The operation mix is 85% reads and 15% writes: people list, profile, family, ancestors (depth 10),
descendants (depth 4), search, relationship path, add person and add relative. The generator
reports its own scheduling lag. If that lag is large, the generator was the bottleneck and the run
is invalid.

## Running it on a dedicated staging host (required before go-live)
The Cloud sandbox is **not** a reliable place to certify capacity: the generator, PostgreSQL and
the API share 4 vCPUs on a shared VM, and identical runs differ widely (see "Results" below).
Procedure:

1. **Hosts.** Use two machines in the same region:
   - **Server host:** at least 4 dedicated vCPUs (not burstable), 8 GB RAM, SSD. PostgreSQL 16 on
     the same host is fine, but record it; production uses managed PostgreSQL. Expect your
     production node count to scale from this result.
   - **Generator host:** at least 2 vCPUs.
2. **Server host setup.** Install the repo, `uv`, PostgreSQL 16 (superuser access for the
   throwaway database) and `openssl`. Set the CPU governor to `performance`, and stop cron jobs,
   backups and other services during the run.
3. **Run on the server host only** (simplest; the generator then shares the CPU, so treat capacity
   as a lower bound):
   ```bash
   PEOPLE=10000 WORKERS=$(nproc) RATES="5,10,20,30,40,60,80" DURATION=120 ops/loadtest/certify.sh
   ```
4. **Or drive it from the generator host** (preferred):
   - on the server host: `SERVE_ONLY=1 ops/loadtest/certify.sh` (seeds, then serves on
     `0.0.0.0:8300` as the RLS role until Ctrl-C; open that port to the generator host only);
   - copy `results/cert-*/state.json` to the generator host;
   - run there:
     ```bash
     uv run python -m app.cli.loadtest sequential --base-url http://SERVER:8300 --state state.json --json seq.json
     uv run python -m app.cli.loadtest sweep --base-url http://SERVER:8300 --state state.json \
       --rates 5,10,20,30,40,60,80 --users 40 --duration 120 --json sweep.json
     ```
5. **Repeat** the sweep at least 3 times, and report the **worst** p95 at each rate. Accept a
   capacity figure only if the three runs agree on it.
6. **Pass criteria** (PRS §49):
   - sequential p95 ≤ 500 ms for every operation;
   - at the expected peak arrival rate (see sizing below), sweep p95 ≤ 500 ms and errors < 1% in all
     three runs;
   - generator lag p99 < 50 ms.
7. **Sizing.** Peak rate ≈ concurrent active users ÷ seconds between their requests. For example,
   300 people active at once, each clicking about every 10 s, is about 30 req/s. Size so that the
   peak rate is at most 70% of the certified capacity.
8. **Record** the result folder (`environment.txt`, `sequential.json`, `sweep.json`) and add a row to
   `docs/release/production-readiness.md`.

## Results in the Cloud sandbox (1 Oct 2026)
**Environment:** 4 vCPU shared VM (cumulative CPU steal observed), 15 GiB RAM, PostgreSQL 16.13. The
API (4 uvicorn workers, RLS app role), PostgreSQL and the generator ran **on the same host**. The
results are evidence for this code. They are **not** a capacity certificate for production
hardware; see the runbook above.

**Sequential (normal use; 1 user, 50 timed calls per operation, 10,000 people; commit `54c1021` plus the seed fix. Later commits changed only overload handling and the generator, which do not affect single-user requests):**

| Operation | p50 ms | p95 ms | p99 ms |
|---|---|---|---|
| People list (page of 50) | 48 | 59 | 156 |
| Person profile | 23 | 28 | 33 |
| Family view | 32 | 44 | 49 |
| Ancestors, depth 10 | 47 | 60 | 64 |
| Descendants, depth 4 | 38 | 50 | 158 |
| Search | 59 | 84 | 161 |
| Relationship path | 82 | 101 | 235 |
| Add person (write) | 34 | 43 | 47 |
| Add relative (write) | 49 | 58 | 64 |

Every operation meets **p95 < 500 ms**, with at least a 5× margin. There were 0 errors.

**Sustained concurrency (open loop, 40 sessions, 60 s per rate; three runs at commit `bb2fb18`; worst of three shown):**

| Arrival rate | Worst p50 ms | Worst p95 ms | Worst p99 ms | Errors | p95 ≤ 500 ms |
|---|---|---|---|---|---|
| 10 req/s | 55 | 125 | 206 | 0% | yes (3/3) |
| 20 req/s | 56 | 134 | 225 | 0% | yes (3/3) |
| 30 req/s | 62 | 180 | 278 | 0% | yes (3/3) |
| 40 req/s | 72 | 248 | 889 | 0% | yes (3/3) |
| 50 req/s | 101 | 353 | 530 | 0% | yes (3/3) |

**Capacity on this shared host: 50 req/s** of the 85/15 read/write mix (three runs agree). Beyond
that:

| Offered | Successful req/s | p95 | Shed (503, `Retry-After`) |
|---|---|---|---|
| 60 req/s | 60.4 | 1.6 s | 0.06–0.25% |
| 70 req/s | 63.0 | 2.5 s | 10% |
| 80 req/s | 62.4 | 2.6 s | 22% |

So the node degrades gracefully: useful throughput holds near its ceiling, there are no timeouts and
no 5xx other than the shed responses.

### Defects found and fixed while certifying
| Finding | Evidence | Fix |
|---|---|---|
| Congestion collapse past capacity: requests queued for the 15-connection pool, waited 30 s, then failed as **unhandled 500s** | 70 req/s offered → 10 successful req/s (29 completed, most of them errors); 80 → 0 successful; 2,389 `QueuePool limit reached` | Per-worker admission control, a 5 s pool wait, and a retryable 503 (`test_overload.py`). Now 63/62 successful req/s, p95 2.5 s, no unhandled errors. |
| Concurrent OCR jobs time out (OpenMP thread thrash) | 1 page: 0.3 s alone, > 300 s with 4 in parallel | `OMP_THREAD_LIMIT=1` per tesseract (`test_concurrent_ocr_jobs_do_not_thrash`) |
| The load test could not write (ADR-0011 attestation) | every write 403 `attestation_required` | Seeded accounts confirm the statement |
| Measurement artifacts, not product defects | re-login per rate (Argon2id: 83 ms × 4 threads each) and keep-alive pinning (19/9/8/4 connections per worker) made identical runs disagree by 3× | The sweep logs in once; one connection per request, like nginx |

### Checked, no change needed
- **N+1 queries:** none. Every endpoint issues 2–16 statements regardless of tree size. Relationship
  path issues one batched query per BFS frontier (bounded by depth).
- **RLS overhead:** not measurable. Sequential medians, RLS role versus owner, three alternating
  rounds: −4.7 to +2.0 ms per endpoint, which is noise.
- **Recursive genealogy queries:** ancestors depth 10 p95 60 ms, descendants depth 4 p95 50 ms.
- **Indexes:** lookups by id and BFS frontiers use indexes (0.1 ms). **Measured trigger:** the people
  list is a sequential scan plus top-N sort, growing linearly with tree size (19 ms at 33,765
  people). Add
  `CREATE INDEX ix_person_tree_display_name ON person (tree_id, preferred_display_name, id) WHERE deleted_at IS NULL`
  before trees reach about 100k people.
- **Serialization and Python overhead:** SQL is 12–52% of request time; the rest is the Python
  stack. Nothing dominates, and nothing missed the target.
- **Worker balancing:** gunicorn with `SO_REUSEPORT` gave no gain (p95 547 vs 463 ms at 50 req/s).
  CPU, not connection distribution, is the limit. Keep `uvicorn --workers`.

### Verdict
- **Met:** `p95 < 500 ms` for normal (sequential) use of every operation, and for sustained load up
  to **50 req/s** on this 4 vCPU shared host, where the database and generator also run.
- **Not claimed:** production capacity. Run `ops/loadtest/certify.sh` on the staging host
  (runbook above) and size the fleet from that result.

## Pilot stack in the sandbox (2 Oct 2026)
The same protocol, now run against the **deployed pilot topology** (ADR-0014): `deploy/pilot/compose.yml`
behind Caddy with TLS (local CA), 4 single-process backend replicas as the RLS app role, 2 workers,
Redis, ClamAV, PostgreSQL 16 in a container standing in for the managed instance (non-superuser
owner). The generator ran on the same 4-vCPU shared host, so this is **still not a dedicated
staging host** and does not certify production capacity. The test image had no Tesseract (no
Debian mirror in the sandbox), so the upload pipeline below excludes OCR.

Commands and raw results: `docs/release/evidence/pilot-2026-10-02/perf/` (`run.sh`, `run.log`,
`sequential.json`, `sweep-{1,2,3}.json`, `overload.json`, `pipeline.json`, `resources.md`,
`per-endpoint.md`). Pipeline benchmark: `ops/loadtest/pipeline_bench.py`.

**Sequential** (1 user, 50 timed requests per operation, 10,000 people): every operation p95 ≤
**195 ms** (people list 195, search 171, relationship path 104, writes ≤ 73). It is slower than the
101 ms measured against uvicorn directly, because the generator opens a new TLS connection per
request (no keep-alive, the same as before), so each request pays a full TLS handshake through
Caddy.

**Sustained (open loop, 3 runs, 40 s per rate):** 0% errors at every rate in all three runs.
Generator lag p99 ≤ 15 ms and no dropped arrivals, so these are server numbers.

| Rate (req/s) | 10 | 20 | 30 | 40 | 50 |
|---|---|---|---|---|---|
| overall p95, runs 1/2/3 (ms) | 104/100/101 | 109/104/106 | 131/127/126 | 189/180/197 | 257/275/287 |
| worst operation p95 of the 3 runs (ms) | 129 | 147 | 206 | 287 | **549** (relationship path) |

- **Overall capacity:** p95 ≤ 500 ms up to **50 req/s**, the same as the 1 Oct native run.
- **Strict per-operation capacity:** every operation's p95 stays under 500 ms in every run up to
  **40 req/s**. At 50 req/s the relationship path reached 549 ms in one run of three.

**Overload, 70 req/s:**
- 9.2% of requests shed as fast `503 server_busy`;
- p95 2.75 s;
- no unhandled errors, no collapse.

**Resources during the sweeps** (5 s samples):

| Container | Typical CPU | Peak CPU | Peak memory |
|---|---|---|---|
| Each backend process | ~25% | ~100–120% | **560–780 MiB** |
| PostgreSQL | 32% | 82% | 404 MiB |
| Caddy | ≤ 18% | — | 44 MiB |
| ClamAV | idle | — | 947 MiB resident |

- Backend memory is about 145 MiB at idle; the 10k-tree traversals and lists grow it.
- **Database:** at most 61 connections (4 × 15 pool budget), 100% buffer-cache hits, 49k commits.

**Pipelines** (`pipeline_bench.py`, through Caddy):

| Workload | Result |
|---|---|
| Property history: 40 events + 6-generation parcel subdivision chain | full record p95 **39 ms**; leaf lineage p95 **27 ms** (100 sequential reads) |
| Document upload: 20 JPEG photos (~1 MB), 5 at a time, 2 workers | upload p95 265 ms; upload → scanned clean + previews p50 10.8 s / p95 17.0 s; **67 documents/min**, queue-bound (OCR excluded) |
| GEDCOM import, 1,000 people (87 KiB) | report 0.2 s; commit **14.3 s** |
| GEDCOM import, 10,000 people (896 KiB) | report 14.8 s; commit **165 s** |
| OCR concurrency | measured natively on 1 Oct: 4 concurrent jobs 0.3 s each after the `OMP_THREAD_LIMIT=1` fix; guarded by `test_concurrent_ocr_jobs_do_not_thrash` |

### Found while measuring (fixed)
1. **Writes committed after the response was sent.**
   - **Root cause:** FastAPI's default dependency scope runs `get_db`'s commit **after** the
     response.
   - **Effects:** a client acting immediately on a 201 could get 404 from another replica (the
     benchmark committed an import right after uploading it). A commit failure was invisible to
     the client, who had already been told it succeeded.
   - **Fix:** `Depends(get_db, scope="function")` commits before responding
     (`test_a_failed_commit_is_an_error_not_a_success` fails without it).
2. **Proxy timeouts shorter than a large import commit.** The 10,000-person commit took 169 s;
   Caddy and nginx gave up at 120 s with a 504 while the import went on to succeed. The import
   upload and commit routes now get 600 s, about 35,000 people at the measured rate.

### Known limitation (trigger recorded)
- **Import commit runs in the request.** It writes about 15–17 ms per person, one request for the
  whole file.
- **Acceptable for the pilot:** typical family GEDCOMs hold hundreds to a few thousand people,
  i.e. seconds to under a minute.
- **Trigger:** if imports above about 20,000 people are expected, or users report long waits,
  move the commit to the job queue with a progress indicator, and batch its inserts.

### Verdict (unchanged in kind)
- **Met in the sandbox:** PRS §49 `p95 < 500 ms` through the full pilot edge for normal use, and
  for sustained load up to 40 req/s (every operation) or 50 req/s (overall p95).
- **Not claimed:** production capacity. The go-live checklist still requires the staging-host run
  above.
- **Pilot sizing:**
  - 4 backend replicas need about 3 GB at peak, ClamAV about 1 GB and the OS 1 GB, so choose a
    **16 GB** VM for 4 replicas; 8 GB fits 2 replicas.
  - A pilot of tens of families is far below 40 req/s.
