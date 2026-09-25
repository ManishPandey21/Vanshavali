# Vanshavali (वंशावली) — agent guide

Indian family-tree / joint-family / ancestral-property application.

## Current state (read before changing anything)

- Frontend only: Vite 6 + React 18 + TypeScript (strict) + Tailwind 4.
- All data is in-memory sample data (`src/data/sampleData.ts`); nothing persists.
- Navigation is a `Page` state switch in `src/App.tsx`, not a router
  (`react-router-dom` is installed but unused; so is `@supabase/supabase-js`).
- No backend, no auth, no tests yet.
- Target architecture, domain model and decisions: `docs/architecture/`.
- Security and privacy baselines: `docs/security/`.

## Commands

```
npm ci
npm run typecheck   # tsc --noEmit
npm run build       # vite build
npm run dev         # http://localhost:3000
```

Run `typecheck` and `build` before every push.

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
