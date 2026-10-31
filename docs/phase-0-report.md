# Phase 0 completion report: Foundation

- Date: 2026-10-31
- Gate (CLAUDE.md, PRD 15): **a test run streams events end to end**
- Result: **passed**, with one intermittent failure recorded below

## Gate evidence

The gate ran with `make e2e` against the full Docker Compose stack, a real Clerk dev instance
and the offline `test` LLM profile (deterministic fake model, no API cost).

| Check | What it proves | Result |
| --- | --- | --- |
| `Backend/tests/system/test_compose_restart.py` | Killing the worker container mid-engine and restarting it finishes the run exactly once: no duplicate event seqs, one version, one artifact | Pass |
| Playwright `run-flow.spec.ts` | Sign in through Clerk, create a project, watch events stream live, approve the spec, see `run_finished` | Pass, 4 of 4 runs |
| Playwright `run-resume.spec.ts` | The same open page keeps streaming while the worker is killed and restarted; the run resumes from its checkpoint and finishes once | Pass 3 of 4 runs (see "Open issues") |

Supporting checks at the same commit range:

- `make check-backend`: lint, format, mypy (strict) and 199 tests pass, against real Postgres,
  Redis, S3 and Docker, including the pipeline crash-resume test.
- `make check-frontend`: lint, typecheck and unit tests pass; studio, admin and site build.
- `make codegen-check`: generated Pydantic models, TS types and API client are up to date.

## What Phase 0 delivered

| Area | Decision record | Summary |
| --- | --- | --- |
| Repo, tooling, CI | ADR-0001 | Two-folder layout, pinned versions, `make dev / check / codegen / migrate / evals / e2e`, GitHub Actions |
| Local storage | ADR-0002 | SeaweedFS as local S3 |
| Shared backend package | ADR-0003 | Settings, JSON logging, UUID v7, feature flags, S3, event keys |
| Schemas and codegen | ADR-0004 | JSON Schema is the single source; Python and TS are generated |
| Data model | ADR-0005 | PRD 9 tables plus idempotency keys; append-only and immutable triggers |
| Auth | ADR-0006 | Clerk JWT verification, just-in-time user provisioning, verified webhooks, personal org |
| LLM gateway | ADR-0007, ADR-0013 | Provider-agnostic interface, role routing in YAML, fallback, per-call cost logging; Gemini, Anthropic, OpenAI and fake adapters |
| Sandbox | ADR-0008 | Locked-down local Docker sandbox with egress allowlist; hosted provider stub |
| Run pipeline | ADR-0009 | LangGraph intake, spec, approval gate, version, engine, finish; Postgres checkpointer; Redis lease and crash recovery |
| Frontend | | Studio (sign-in, projects, prompt box, three-panel studio, live build log, spec approval), admin console, Astro site |

## Deviations from the plan

- **Phase 1 started before this gate passed** (owner-approved, 2026-10-30), because the gate was
  blocked only on Clerk keys. Phase 1 work is backend-only or behind `FEATURE_PHASE1_OBJECTS`:
  CAD engine (ADR-0010), printability engine (ADR-0011), mechanical agent (ADR-0012) and the
  100-case objects eval suite. All of it passes `make check-backend`.
- **Model provider:** the owner chose Google Gemini over Anthropic (ADR-0013). Until the Gemini
  key has billing enabled, every role runs on `gemini-3.8-flash`.

## Open issues

1. **Intermittent `POST /v1/projects` hang (not reproduced).** On the first `make e2e` against a
   freshly built stack, `run-resume` timed out: the create-project request reached the API and
   never answered, with no error logged while health checks kept passing. Three later runs
   passed. If it recurs, capture `docker compose logs api` and a Postgres `pg_stat_activity`
   snapshot during the hang.
2. **CI secrets.** GitHub repository secrets for Clerk are not set yet, so CI cannot run the
   Playwright step. Needed: `CLERK_ISSUER`, `CLERK_SECRET_KEY`, `CLERK_WEBHOOK_SIGNING_SECRET`,
   `VITE_CLERK_PUBLISHABLE_KEY`, `E2E_CLERK_USER_EMAIL`.

## Carried into later phases

Studio bundle size (about 610 kB) before the 1 Mbps target; per-job egress enforcement in the
hosted sandbox; upload scanning, rate limits and credit checks; OpenTelemetry. Details in
`docs/HANDOFF.md`.

## Decisions awaiting owner review

Listed in `docs/HANDOFF.md` under "Decisions waiting for your review".
