SHELL := bash
.SHELLFLAGS := -eu -o pipefail -c
.DEFAULT_GOAL := help

BE := cd Backend &&

.PHONY: help check check-backend

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*## /\t/'

check: check-backend  ## Lint + type check + tests (run before every commit)

check-backend:  ## Backend lint, types, unit tests
	$(BE) uv sync --frozen -q
	$(BE) uv run ruff check .
	$(BE) uv run ruff format --check .
	$(BE) uv run mypy .
	$(BE) uv run pytest -q
