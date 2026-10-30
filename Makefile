SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

BE := cd Backend &&
FE := cd Frontend &&
COMPOSE := docker compose
GENERATED := Backend/schemas/kehora_schemas/generated Backend/api/openapi.json \
	Frontend/packages/types/src/generated Frontend/packages/api-client/src/generated
gen_sum = find $(GENERATED) -type f -not -path '*__pycache__*' | sort | xargs sha256sum | sha256sum

.PHONY: help dev down logs check check-backend check-frontend e2e services migrate codegen codegen-check evals

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

dev:  ## Build and start everything: data services, api, worker, studio, admin, site
	$(COMPOSE) up -d --build --wait
	@echo ""
	@echo "  studio  http://localhost:5173"
	@echo "  admin   http://localhost:5174"
	@echo "  site    http://localhost:4321"
	@echo "  api     http://localhost:8000/docs"

down:  ## Stop everything (keeps data volumes)
	$(COMPOSE) down

logs:  ## Follow api and worker logs
	$(COMPOSE) logs -f api worker

check: codegen-check check-backend check-frontend e2e  ## Lint + types + unit/integration + Playwright (run before every commit)

check-backend: services  ## Backend lint, types, unit and integration tests
	$(BE) uv sync --frozen -q
	$(BE) uv run ruff check .
	$(BE) uv run ruff format --check .
	$(BE) uv run mypy .
	$(BE) uv run pytest -q

check-frontend:  ## Frontend lint, types, unit tests
	$(FE) pnpm install --frozen-lockfile --silent
	$(FE) pnpm lint
	$(FE) pnpm typecheck
	$(FE) pnpm test

services:  ## Start Postgres, Redis, local S3 and the sandbox egress proxy (needed by tests)
	$(COMPOSE) up -d --build --wait postgres redis s3 egress

migrate:  ## alembic upgrade head
	$(BE) cd db && uv run alembic upgrade head

codegen:  ## Regenerate Pydantic models, TS types and API client from Backend/schemas + OpenAPI
	$(BE) bash scripts/codegen_py.sh
	$(BE) uv run python scripts/export_openapi.py
	$(FE) cd packages/types && node scripts/codegen.mjs ../../../Backend/schemas
	$(FE) pnpm --filter @kehora/api-client codegen

codegen-check:  ## Fail if generated code is stale (regenerates, compares checksums)
	@before=$$($(gen_sum)); \
	$(MAKE) -s codegen >/dev/null 2>&1; \
	after=$$($(gen_sum)); \
	if [ "$$before" != "$$after" ]; then \
		echo "Generated code was stale and has been regenerated; review and commit it."; exit 1; \
	fi; echo "codegen: up to date"

e2e:  ## Gate flows against the compose stack (offline LLM): restart system test + Playwright
	LLM_ROUTING_PROFILE=test ECHO_DELAY_S=4 $(COMPOSE) up -d --build --wait
	$(BE) uv run pytest -q -m system tests/system
	$(FE) pnpm e2e

evals:  ## Agent eval suites (Phase 1 adds the object prompts)
	$(BE) uv run python -m evals
