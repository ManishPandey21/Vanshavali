# Implementation status

Status vocabulary: `NOT_STARTED`, `IN_PROGRESS`, `PARTIAL`, `IMPLEMENTED`, `VERIFIED` (automated
tests exist **and pass**), `BLOCKED`, plus `DEFERRED` (intentionally postponed, with the phase named).
Requirement-level mapping: [docs/requirements-traceability.md](docs/requirements-traceability.md).

Last verified: 2026-09-25.
- Backend: `uv run pytest` 142 passed; ruff and mypy clean.
- Frontend: lint, typecheck, Vitest and build green.
- Playwright: core flow green.

## Platform / Phase 0

| Module | Status | Tests | Notes |
|---|---|---|---|
| Repository layout, ADRs 0001–0010, implementation plan | VERIFIED | docs | `docs/architecture/` |
| Config (12-factor, prod safety checks) | VERIFIED | indirect | Production refuses dev keys, the test scanner or insecure cookies |
| DB + Alembic (3 migrations, composite tree FKs, append-only audit trigger) | VERIFIED | `test_migrations.py` | upgrade → check → downgrade → upgrade |
| Auth: register/login/logout, Argon2id, server sessions, CSRF, rate limits, session revocation, password change | VERIFIED | `test_auth.py` (13) | Email verification and password reset DEFERRED (needs an email provider) |
| MFA (TOTP) | VERIFIED | `test_auth.py` | RFC 6238 vectors |
| Trees, memberships, roles, invitations, grants, audit API | VERIFIED | `test_trees.py` (12) | Invitation email = console outbox (ASSUMPTION) |
| Authorisation (deny by default, branch scope, 404 isolation) | VERIFIED | `test_route_isolation.py` (every tree route), `test_privacy.py` | RLS as a second barrier DEFERRED (Phase 8) |
| Privacy engine (levels, field groups, living/minor rules, public mode) | VERIFIED | `test_privacy.py` (12) | |
| Encrypted write-once storage (local / S3), scanner (clamd / EICAR test), upload validation, jobs (sync / RQ) | VERIFIED | `test_documents.py` | Orphan-object cleanup job DEFERRED |
| Docker (backend, frontend/nginx), docker-compose (postgres, redis, minio, clamav, worker) | IMPLEMENTED | CI `docker` job builds both images; `compose config` validated | Full compose stack not exercised in the dev sandbox (no Docker daemon) |
| CI (backend, frontend, e2e, security audits + SAST, docker) | IMPLEMENTED | GitHub Actions | |
| Demo seed | VERIFIED | `test_seed.py`, CI seed step | Fictional family |

## Phase 1: Core genealogy MVP

| Module | Status | Tests | Notes |
|---|---|---|---|
| Persons, flexible names (scripts, as-recorded), soft delete / restore | VERIFIED | `test_genealogy.py` | |
| Events + genealogical dates/times (precision, calendars, time source) | VERIFIED | `test_genealogy.py` | |
| Places (hierarchy, local/historical names) | VERIFIED | `test_genealogy.py`, `test_search_consent.py` | Geocoding service DEFERRED |
| Relationships (typed edges, unions, adoption/step/foster/guardian, cycle prevention) | VERIFIED | `test_genealogy.py` | |
| Family view, ancestors/descendants (CTE), relationship calculator | VERIFIED | `test_genealogy.py`, `test_privacy.py` | Closure tables DEFERRED until load tests |
| Sources, citations, evidence status, traditional registers | VERIFIED | `test_heritage_family.py` | |
| Search (transliteration, trigram, phonetic, match reasons) | VERIFIED | `test_search_consent.py` | OpenSearch DEFERRED (ADR-0007) |
| Frontend: auth, trees, people, add person/relatives, profile, tree viewer, relationship calculator, admin screens | VERIFIED | Vitest (43), Playwright core flow | |

## Phase 2: Indian family model

| Module | Status | Tests | Notes |
|---|---|---|---|
| Heritage assertions/profiles (person and branch; no inference; disputes) | VERIFIED | `test_heritage_family.py` (12) | |
| Households (membership over time, karta) and branches (descent-rule derivation) | VERIFIED | `test_heritage_family.py` | |
| Migration events | VERIFIED | `test_genealogy.py` | Migration **map** DEFERRED |
| Multilingual UI (en, hi) | IMPLEMENTED | Vitest locale parity test | More languages DEFERRED (PRS §51) |

## Phase 3: Documents and evidence

| Module | Status | Tests | Notes |
|---|---|---|---|
| Document vault (upload pipeline, vault class, previews, versions, links, signed downloads, soft delete/restore) | VERIFIED | `test_documents.py` (17) | Streaming large downloads, retention purge and watermarking DEFERRED |
| OCR (PDF text layer, Tesseract eng+hin) + extractors (birth certificate, Kundli, land record) + Aadhaar masking | VERIFIED | `test_extraction.py` (15) | Handwriting / other Indic OCR languages DEFERRED |
| Proposal review → new claims with citation + provenance | VERIFIED | `test_extraction.py` | |
| Frontend: document vault, extraction review | IN_PROGRESS | — | Second frontend pass |

## Phase 4: Astrology

| Module | Status | Tests | Notes |
|---|---|---|---|
| Astrology profiles, provenance, privacy, birth-conflict report | VERIFIED | `test_astrology.py` (5), `test_extraction.py` | Ephemeris calculation engine DEFERRED |
| Frontend: astrology tab, conflicts | IN_PROGRESS | — | |

## Phase 5: Ancestral property

| Module | Status | Tests | Notes |
|---|---|---|---|
| Property, parcels (Indian identifiers, ULPIN, units), interests (exact shares), events, partition, timeline, lineage | VERIFIED | `test_property.py` (12) | Event undo, and interest carry-over on subdivision, DEFERRED |
| Frontend: property register and timeline | IN_PROGRESS | — | |

## Phase 6: GEDCOM

| Module | Status | Tests | Notes |
|---|---|---|---|
| GEDCOM 5.5/5.5.1/7 import (staging, report, duplicates, decisions, extension preservation) | VERIFIED | `test_gedcom.py` (17) | GEDZIP/media import DEFERRED; large imports run synchronously |
| GEDCOM 7 export (SCHMA `_IND_*` URIs, privacy-filtered) | VERIFIED | `test_gedcom.py` incl. round trip | |
| Full archival ZIP (manifest, media, JSON) | DEFERRED | — | Phase 8 (PRS §43) |
| Frontend: import/export | IN_PROGRESS | — | |

## Phase 7: Search and discovery

| Module | Status | Tests | Notes |
|---|---|---|---|
| Duplicate candidates | VERIFIED | `test_search_consent.py` | |
| Reversible merge (preview, admin approval, undo) | VERIFIED | `test_merge.py` | Frontend merge dialog IN_PROGRESS |

## Privacy and compliance

| Module | Status | Tests | Notes |
|---|---|---|---|
| Consent ledger, profile claims, erasure, account closure | VERIFIED | `test_search_consent.py`, `test_privacy.py` | Formal data-subject-request inbox and grievance contact DEFERRED (legal workstream) |

## Phase 8: Hardening (not yet started unless noted)

| Item | Status |
|---|---|
| RLS second barrier | DEFERRED |
| Load tests (10k-person tree, p95 targets) | DEFERRED |
| WCAG 2.2 AA audit | DEFERRED (keyboard navigation and a text alternative for the tree exist) |
| Observability (structured logs, traces, alerts) | DEFERRED |
| Backup/restore drill | PARTIAL (runbook in `docs/operations/backup-restore.md`) |
| DAST / penetration test | DEFERRED |
| Collaboration (change proposals, comments, notifications) | DEFERRED (post-MVP) |
| Reports / PDF charts / fan chart / maps | DEFERRED |
