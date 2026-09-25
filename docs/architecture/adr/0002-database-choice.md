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
7. **Row-level security is a second isolation barrier** (Phase 8, migration `b7c1e0d2f3a4`). Every
   tree-scoped table (`app/models/rls.py::RLS_TABLES`) has RLS enabled and a `tree_isolation`
   policy: `tree_id = current_setting('app.tree_id')`, applied to reads (`USING`) and writes
   (`WITH CHECK`). With no tree bound, the policy matches nothing, so access fails closed.
   - `app.core.db.bind_tree()` sets `app.tree_id` **transaction-locally** (`set_config(..., true)`).
     A session `after_begin` hook re-applies it at the start of each transaction, so a pooled
     connection never carries one request's tree into the next.
   - The tree context loaders (`load_tree_context`, `load_public_context`) bind the tree after the
     membership check. Background jobs bind the tree of the job they process.
   - The API and workers connect as a **non-owner role** (`vanshavali_app`: `NOSUPERUSER
     NOBYPASSRLS`), which the policies apply to. Policies are *not* `FORCE`d, so the table owner
     (migrations, backup/restore, `app.cli.benchmark` bulk loads) is unaffected.
     `python -m app.cli.ensure_app_role` creates the role and its grants idempotently.
   - Tables read before a tree is known (`tree`, `tree_membership`, `tree_invitation`, `app_user`,
     `user_session`, `auth_token`) and the append-only `audit_event` are not covered. The service
     layer protects them.

## Consequences
- The composite FKs make every foreign key two columns wide. The ORM helpers hide this.
- RLS means a service bug that forgets a `tree_id` filter returns nothing from another tree, rather
  than leaking it (`tests/test_rls.py`). The cost is one `set_config` per transaction, which is
  negligible. Any new tree-scoped table must be added to `RLS_TABLES`; a test fails otherwise.
- A deployment that connects the app as the owner or a superuser silently loses the barrier.
  Deployment docs require the separate role, and `/health/ready` reports it.
- A graph database (Neo4j) would be added only as a *read projection*, under a new ADR, and only if
  benchmarks at 100k people miss the PRS §49 p95 targets.

## Alternatives rejected
Neo4j as the primary store (weak fit for transactional property/ledger data, migrations and
reporting). A document DB (relational integrity is essential here). Closure tables now (premature,
since they add write amplification before any read problem is measured).
