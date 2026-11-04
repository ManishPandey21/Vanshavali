# Developer shortcuts. See README.md for the full setup.
.PHONY: backend-install backend-test backend-lint migrate seed api frontend-install frontend-test frontend-build e2e a11y check

backend-install:
	cd backend && uv sync

backend-lint:
	cd backend && uv run ruff check app tests && uv run ruff format --check app tests && uv run mypy app

backend-test:
	cd backend && uv run pytest -q

migrate:
	cd backend && uv run alembic upgrade head

# Dev/test only. Needs VSH_DEMO_PASSWORD and VSH_SUPERADMIN_PASSWORD (docs/operations/dev-accounts.md).
seed:
	cd backend && uv run python -m app.cli.seed_demo

api:
	cd backend && uv run uvicorn app.main:app --reload --port 8000

frontend-install:
	cd frontend && npm ci

frontend-test:
	cd frontend && npm run lint && npm run typecheck && npm test

frontend-build:
	cd frontend && npm run build

e2e:
	cd e2e && npx playwright test

# Accessibility audit only (axe WCAG 2.2 A/AA + keyboard/semantics checks); see docs/accessibility/.
a11y:
	cd e2e && npx playwright test a11y

check: backend-lint backend-test frontend-test frontend-build
