# ADR-0002: PostgreSQL as canonical store; every row is tree-scoped

- Status: Proposed
- Date: 2026-09-25

## Context
Today everything is in memory (see architecture README F8). We need durable, transactional storage
that keeps each family's tree strictly isolated. We also need recursive lineage queries and a clean
upgrade path through migrations.

## Decision
1. **PostgreSQL** is the single canonical store. We do not use a graph database. Recursive CTEs
   handle ancestry, and a graph projection may be added later only as a read-only derived view,
   under its own ADR.
2. **Tree = tenant.** Every domain table has `tree_id NOT NULL`. Foreign keys are composite
   `(tree_id, id)`, so a row can't reference data in another tree.
3. **Defense in depth:** the service layer always filters by the tree the caller is authorised
   for. Postgres Row-Level Security policies on `tree_id` act as a second barrier, using a
   per-request `SET LOCAL app.tree_id`.
4. **Migrations only** (Alembic if the backend is Python; see open question Q1). Every migration has
   a downgrade and is tested in CI with upgrade → downgrade → upgrade on an empty DB and on a seeded
   one.
5. IDs are UUIDv7, never sequential integers, so identifiers can't be enumerated.

## Consequences
- Cross-tree person linking (the same ancestor appearing in two families' trees) needs an explicit
  "link" feature later. Rows are never shared across trees.
- RLS adds some operational complexity. Tests must run as the non-superuser app role, or the RLS
  policies are bypassed and go untested.

## Alternatives considered
- *Neo4j/graph DB as primary:* natural fit for traversal, but a poor fit for transactional
  integrity, migrations, property/ledger data and team familiarity.
- *Supabase (Postgres + RLS + auth):* compatible with this ADR. Whether to use it is Q1.
