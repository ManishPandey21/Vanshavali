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
VSH_DATABASE_URL=… uv run python -m app.cli.benchmark --people 10000
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
- **Relationship path:** add a closure table or bidirectional LCA if production p95 exceeds 500 ms.
- **Duplicates:** move to a background job with cached results for trees over 20k people.
- **Tree size:** repeat with 100k people and over HTTP (uvicorn workers) before choosing a graph
  projection (ADR-0002).
