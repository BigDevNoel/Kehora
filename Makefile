SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

BE := cd Backend &&
COMPOSE := docker compose

.PHONY: help check check-backend services migrate codegen codegen-check

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

check: check-backend  ## Lint + type check + tests (run before every commit)

check-backend: services  ## Backend lint, types, unit tests
	$(BE) uv sync --frozen -q
	$(BE) uv run ruff check .
	$(BE) uv run ruff format --check .
	$(BE) uv run mypy .
	$(BE) uv run pytest -q

codegen:  ## Regenerate Pydantic models, TS types and API client from Backend/schemas + OpenAPI
	$(BE) bash scripts/codegen_py.sh

codegen-check: codegen  ## Fail if generated code is out of date
	git diff --exit-code -- Backend/schemas/kehora_schemas/generated

services:  ## Start Postgres, Redis and local S3 (needed by tests)
	$(COMPOSE) up -d --build --wait postgres redis s3

migrate:  ## alembic upgrade head
	$(BE) cd db && uv run alembic upgrade head
