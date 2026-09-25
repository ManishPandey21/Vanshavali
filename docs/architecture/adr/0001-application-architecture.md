# ADR-0001: Application architecture — modular monolith, React SPA + FastAPI

- Status: Accepted · Date: 2026-09-25

## Context
The repository has a Vite + React prototype and no backend. The PRS asks for a long-lived family
archive with strict privacy rules, asynchronous document processing, and a small team. The
suggested baseline was Next.js + FastAPI.

## Decision
1. **One backend deployable** (FastAPI) organised into domain modules (`backend/app/modules/*`), plus
   an RQ **worker** process built from the same codebase for scanning, OCR, extraction, import and
   export.
2. **Frontend: React SPA built with Vite** (kept from the repo), with React Router, TanStack Query,
   i18next and Tailwind. It is served as static files. All data comes from `/api/v1` using cookie
   sessions.
3. The API is the only contract. Frontend types are generated from the OpenAPI document.

### Why Vite SPA instead of Next.js
| Concern | Next.js | Vite SPA |
|---|---|---|
| Private-data leakage via HTML/hydration (PRS §58 privacy AC) | SSR/RSC serialises data into HTML/flight payloads; every page must be audited | HTML shell contains no data; only authorised JSON reaches the browser |
| SEO | Useful for public pages | Public trees are opt-in and deceased-only; SEO not a requirement (and indexing is discouraged for vault content) |
| Ops | Needs a Node server alongside FastAPI (two app runtimes, cookie forwarding) | Static assets on nginx/CDN |
| Existing code | Rewrite | Evolve |

We would reconsider Next.js if public, SEO-indexed deceased-ancestor pages became a product goal.
Even then, a separate small SSR app for public pages would be the better fit.

## Consequences
- The backend module boundaries are enforced by convention and review: routers call their own
  services, and there are no cross-module table writes.
- Scaling path: run more API replicas and more workers. Services only get split out once they have
  a measured need to deploy separately.

## Alternatives rejected
Microservices (premature). Django (FastAPI and Pydantic give typed OpenAPI with less weight, and we
don't need Django's server-rendered admin for private family data). GraphQL (REST with explicit
authorisation per endpoint is easier to audit).
