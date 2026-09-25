# ADR-0002: PostgreSQL as the canonical store; every row is tree-scoped

- Status: Accepted · Date: 2026-09-25

## Decision
1. **PostgreSQL 16** is the only source of truth. Extensions: `pg_trgm` and `unaccent`.
2. **Tree = tenant.** Every domain table has `tree_id NOT NULL`. Foreign keys between tree-scoped
   entities are **composite `(tree_id, id)`**, so a row can't reference another tree even if a
   service has a bug.
3. Primary keys are **UUIDv7**: time-ordered for index locality, and they can't be enumerated.
4. Family graph traversal uses **recursive CTEs** over an indexed relationship-edge table, with depth
   limits and cycle guards. The relationship calculator runs in application memory over the
   tree's edge list.
5. Schema changes are made **only through Alembic migrations**. CI checks upgrade → `alembic check` →
   downgrade → upgrade from an empty database.
6. The audit table is append-only, enforced by a trigger that rejects UPDATE and DELETE.

## Consequences
- The composite FKs make every foreign key two columns wide. The ORM helpers hide this.
- **DEFERRED to Phase 8:** row-level security keyed on `app.tree_id` as a second isolation barrier.
- A graph database (Neo4j) would be added only as a *read projection*, under a new ADR, and only if
  benchmarks at 100k people miss the PRS §49 p95 targets.

## Alternatives rejected
Neo4j as the primary store (weak fit for transactional property/ledger data, migrations and
reporting). A document DB (relational integrity is essential here). Closure tables now (premature,
since they add write amplification before any read problem is measured).
