SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

BE := cd Backend &&
FE := cd Frontend &&
COMPOSE := docker compose
GENERATED := Backend/schemas/kehora_schemas/generated Backend/api/openapi.json \
	Frontend/packages/types/src/generated Frontend/packages/api-client/src/generated
gen_sum = find $(GENERATED) -type f -not -path '*__pycache__*' | sort | xargs sha256sum | sha256sum

.PHONY: help check check-backend check-frontend services migrate codegen codegen-check

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

check: codegen-check check-backend check-frontend  ## Lint + type check + tests (run before every commit)

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
