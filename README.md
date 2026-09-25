# Vanshavali (वंशावली)

A **privacy-first Indian Family Heritage Graph**. It combines genealogy, joint-family
households and branches, multilingual and historical names, ancestral villages, birth
date/time/place with precision, Kundli/astrology records, source evidence and provenance, a
secure document vault with reviewed OCR, ancestral property and land records, and GEDCOM 7
interoperability.

- Product spec: PRS v1.0, summarised with a status for each requirement in
  [docs/requirements-traceability.md](docs/requirements-traceability.md).
- Architecture: [docs/architecture/implementation-plan.md](docs/architecture/implementation-plan.md),
  [ADRs](docs/architecture/adr/README.md), [domain model](docs/architecture/domain-model.md),
  [data model](docs/architecture/data-model.md).
- Security: [threat model](docs/security/threat-model.md), [privacy model](docs/security/privacy-model.md).
- Status: [IMPLEMENTATION_STATUS.md](IMPLEMENTATION_STATUS.md).

## Repository layout
```
backend/    FastAPI modular monolith (Python 3.11, SQLAlchemy 2, Alembic, RQ worker)
frontend/   React 18 + TypeScript SPA (Vite, React Router, TanStack Query, i18next: en, hi)
e2e/        Playwright end-to-end tests (drive the real frontend against the real backend)
docs/       architecture, ADRs, security, operations, GEDCOM extension vocabulary
docker-compose.yml   postgres, redis, minio, clamav, migrate, backend, worker, frontend
```

## Quick start (Docker)
```bash
cp .env.example .env            # set keys: see comments in the file
docker compose up --build       # app on http://localhost:8080, API docs on :8000/api/v1/docs
docker compose run --rm backend python -m app.cli.seed_demo   # optional demo family
```
Demo login after seeding: `demo@vanshavali.local` / `demo-password-123` (fictional data).

## Local development (without Docker)
Prerequisites: Python 3.11 + [uv](https://docs.astral.sh/uv/), Node 22, PostgreSQL 16 (with the
`pg_trgm` and `unaccent` extensions available), Redis (optional in dev), and Tesseract OCR with
the `eng` and `hin` language packs.

```bash
# database
createuser -s vanshavali && createdb -O vanshavali vanshavali   # password: vanshavali (dev only)

# backend
cd backend
uv sync
uv run alembic upgrade head
uv run python -m app.cli.seed_demo        # optional
uv run uvicorn app.main:app --reload --port 8000

# frontend (another terminal)
cd frontend
npm ci
npm run dev                               # http://localhost:3000 (proxies /api to :8000)
```
Development defaults (`backend/app/core/config.py`, all overridable with `VSH_*` environment
variables): local encrypted file storage in `backend/var/storage`, jobs run inline
(`VSH_JOB_MODE=sync`), and an EICAR-only test scanner. **`VSH_ENV=production` refuses to start**
with dev keys, the test scanner or insecure cookies.

## Quality gates
```bash
make backend-lint backend-test      # ruff, mypy, pytest (uses local Postgres; creates vanshavali_test)
make frontend-test frontend-build   # eslint, tsc, vitest, vite build
make e2e                            # Playwright
```
Backend tests expect a PostgreSQL role `vanshavali`/`vanshavali` that is allowed to create
databases. Point `VSH_TEST_ADMIN_URL` elsewhere if needed. CI runs all of the above plus
dependency audits and Docker builds (`.github/workflows/ci.yml`).

## Key principles
- **Server-side authorisation everywhere.** Deny by default. Other trees' data returns 404.
- **Living people are private by default.** Minors are never public. Field-level privacy applies.
- **Evidence over certainty.** Competing claims are kept, with sources, citations, evidence status
  and provenance.
- **No cultural inference.** Gotra, caste, community or religion are never derived from surnames,
  places or relatives.
- **OCR/AI output is a proposal**, and only human review turns it into facts.
- **Property records are documentary, not a legal title opinion.**
