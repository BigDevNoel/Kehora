# ADR-0001: Pinned toolchain and library versions

- Status: accepted
- Date: 2026-10-30

## Context

PRD section 4 asks us to pin exact versions at project start and record them here.
Lockfiles (`Frontend/pnpm-lock.yaml`, `Backend/uv.lock`) hold the full resolved tree;
this ADR records the direct, load-bearing choices.

## Decision

### Runtimes and services

| Item | Version |
| --- | --- |
| Node.js | 24 LTS |
| pnpm | 9.12 |
| Python | 3.12 (installed by uv) |
| uv | 0.12 |
| PostgreSQL | 16, image `postgis/postgis:16-3.5` + `postgresql-16-pgvector` |
| Redis | 7.4 |
| SeaweedFS | `chrislusf/seaweedfs:4.51` (local S3, see ADR-0002) |

### Frontend

| Package | Version |
| --- | --- |
| react / react-dom | 19.3.1 |
| vite | 8.3.5 |
| @vitejs/plugin-react | 6.1.2 |
| typescript | 6.0.3 (not 7.x: typescript-eslint peer range is `<6.1.0`) |
| @tanstack/react-router / router-plugin | 1.170.46 / 1.168.48 |
| @tanstack/react-query | 5.105.0 |
| tailwindcss / @tailwindcss/vite | 4.3.3 |
| astro / @astrojs/node | 7.4.4 / 11.1.9 |
| @clerk/react | 6.18.3 |
| @clerk/testing | 2.2.52 |
| @playwright/test | 1.64.1 |
| openapi-typescript / openapi-fetch | 7.13.0 / 0.17.0 |
| json-schema-to-typescript | 16.0.0 |
| @microsoft/fetch-event-source | 2.0.1 |
| @sentry/react | 11.10.0 |
| eslint / typescript-eslint | 10.13.0 / 8.72.1 |
| vitest | 5.0.5 |

### Backend

| Package | Version |
| --- | --- |
| fastapi | 0.162.0 |
| uvicorn | 0.54.0 |
| pydantic / pydantic-settings | 2.14.2 / 2.16.2 |
| sqlalchemy | 2.1.6 |
| alembic | 1.20.1 |
| psycopg (binary, pool) | 3.3.6 |
| langgraph / langgraph-checkpoint-postgres | 1.2.18 / 3.2.0 |
| arq | 0.28.0 |
| redis | 8.1.0 |
| anthropic / openai | 2.3.0 / 3.41.0 (imported only in `Backend/llm/`) |
| boto3 | 1.43.122 |
| pyjwt[crypto] | 2.15.1 |
| svix | 2.9.1 |
| sentry-sdk / langsmith | 2.73.0 / 0.14.16 |
| structlog | 26.1.0 |
| uuid-utils | 1.2.0 (UUID v7; Python 3.12 has no `uuid.uuid7`) |
| docker | 7.2.0 |
| datamodel-code-generator | 0.87.0 |
| ruff / mypy / pytest | 0.17.3 / 2.4.1 / 9.2.0 |

Note: the Phase 0 plan listed earlier majors (Vite 7, Astro 5, SQLAlchemy 2.0). Current stable
releases at project start are Vite 8, Astro 7 and SQLAlchemy 2.1; we take those.

## Consequences

Upgrades are deliberate: bump in the manifest, regenerate the lockfile, run `make check`, and
update this table in the same commit.
