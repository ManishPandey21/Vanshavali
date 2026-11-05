# Vanshavali (वंशावली) — agent guide

Indian family-tree / joint-family / ancestral-property application.

## Current state (read before changing anything)

Modular monolith (ADR-0001):

- `backend/` — FastAPI + SQLAlchemy 2 + Alembic on PostgreSQL 16, Redis/RQ jobs (`JOB_MODE=sync`
  runs them inline). Domain modules in `backend/app/modules/*` (identity, trees, genealogy, heritage,
  family, evidence, documents, extraction, astrology, property, gedcom, merge, archive, search,
  consent, public, smartadd, masterdata). All authorisation and field redaction live in `backend/app/authz`; the server is
  the authority. Platform capabilities (`authz/platform.py`, ADR-0025) are separate from tree permissions: a system admin
  curates global master data at `/admin/master-data` and still has no tree access. API under `/api/v1`, structured errors `{error: {code, message, details}}`.
- `frontend/` — Vite 6 + React 18 + TypeScript (strict) SPA: React Router, TanStack Query,
  i18next (`src/i18n/locales/en.json`, `hi.json`, kept key-identical by a test), Tailwind 4.
  API types are generated from OpenAPI (`npm run gen:api` → `src/api/schema.d.ts`); the fetch
  wrapper (`src/api/client.ts`) sends cookies and the `X-CSRF-Token` double-submit header.
  UI permission checks (`my_permissions`, `can_edit`) only hide controls; 403s are handled.
  Suggestion lists come from the master-data service (ADR-0018, `useVocabulary`, `SmartSelect`);
  `src/data/masterData/*` remain only as fallbacks until removed. Never used to infer values.
- `e2e/` — Playwright specs against the real stack (own `vsh_e2e` database, API :8100, SPA :3100).
- `deploy/pilot/` — staging/pilot stack (ADR-0014: one VM with Compose + managed PostgreSQL and S3):
  Caddy edge, scripts (deploy, rollback, backup, restore), monitoring, and a staging drill. Runbooks
  in `docs/operations/`, go-live checklist in `docs/release/pilot-go-live-checklist.md`.
- Architecture, domain model and decisions: `docs/architecture/`. Security/privacy: `docs/security/`.

## Commands

```
# backend (from backend/)
uv sync && uv run alembic upgrade head && uv run python -m app.cli.masterdata load
uv run uvicorn app.main:app --port 8000
uv run pytest -q

# frontend (from frontend/; dev server proxies /api → :8000)
npm ci
npm run dev         # http://localhost:3000
npm run lint && npm run typecheck && npm test && npm run build
npm run gen:api     # regenerate openapi.json + src/api/schema.d.ts after API changes

# end-to-end (from e2e/; starts backend + frontend itself)
npm ci && npx playwright test
```

Run lint, typecheck, tests and build before every push; `make check` runs the whole set.

## Working rules

1. **Explore before building.** Look for existing patterns and modules before adding new ones.
   Use the smallest set of skills that helps with the task.
2. **Decisions go in ADRs.** Changes to relationship modelling, privacy, RBAC, document storage,
   GEDCOM, property modelling, OCR/AI provenance, households or large-tree rendering need an ADR in
   `docs/architecture/adr/` before code. Stress-test the ADR first (grill-me). Check
   `docs/architecture/open-questions.md`.
3. **The relational schema is canonical.** The graph/Mermaid domain model in
   `docs/architecture/domain-model.md` explains it and must be kept in sync. It never replaces the
   schema without an ADR.
4. **All DB changes go through Alembic migrations**, each with a downgrade. Never hand-edit a database schema.
5. **Security-sensitive changes** (auth, authz, public trees, downloads, share links, living/child
   data, property docs, exports, uploads, admin) must update `docs/security/threat-model.md` /
   `privacy-model.md` and include negative tests: IDOR/BOLA, cross-tree access, privilege
   escalation, unauthorised download, living-person leakage, signed-URL abuse, malicious upload.
6. **APIs**: versioned (`/api/v1`), typed request/response schemas (never raw ORM models),
   cursor pagination, structured errors, authorisation on every handler, OpenAPI published,
   frontend types generated from OpenAPI.
7. **Documents/OCR**: original → validate → malware scan → immutable storage → OCR → extraction →
   *proposed* data → human review → confirmed fact + citation. OCR/AI output never overwrites
   canonical data directly.
8. **Testing**: unit, integration, authz, migration, component and Playwright E2E. Every material bug
   fix gets a regression test. A passing API test does not prove the browser workflow works. See
   the critical E2E flows in `docs/architecture/README.md`.
9. **Frontend**: accessible, responsive, mobile-first, handles Indic scripts, uses progressive disclosure.
   Prefer genealogy-specific interactions over generic admin-dashboard patterns.
