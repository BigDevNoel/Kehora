# Phase 0 handoff

Last updated: 2026-10-31. Status: **Phase 0 gate passed** on 2026-10-31 with a real Clerk dev
instance: the restart system test and both Playwright specs pass (3 of 4 runs; see the flake
under known follow-ups). Phase 1 backend work (CAD, printability, objects evals, mechanical
agent) is built and verified.

## Phases (CLAUDE.md / PRD 15)

There are 7 phases, numbered 0 to 6:

| # | Phase | Gate |
| --- | --- | --- |
| 0 | Foundation (this one) | A test run streams events end to end |
| 1 | 3D objects | 90% of `Backend/evals/objects` pass |
| 2 | Electronics + enclosures | Device evals 70% first run, 90% after repairs |
| 3 | Complete devices (apps, robots, laser/CNC, guides, photo-to-part, molds) | All templates pass |
| 4 | Making and commerce (orders, payments, maker network, escrow) | End-to-end test order in staging |
| 5 | Marketplace, schools, full admin | Indexable listings + 30-kit school order |
| 6 | Mobile apps | n/a |

## What was built

| Area | Where | Notes |
| --- | --- | --- |
| Repo layout, Makefile, compose, CI | root, `.github/workflows/ci.yml` | `make dev / check / codegen / migrate / evals / e2e` |
| Pinned versions | ADR-0001 | Vite 8, Astro 7, TS 6.0 (typescript-eslint caps at <6.1), SQLAlchemy 2.1 |
| Local S3 | ADR-0002 | SeaweedFS: MinIO no longer publishes a public image |
| Shared backend package | `Backend/common`, ADR-0003 | settings, JSON logging, UUID v7, flags, S3, event keys |
| Schemas and codegen | `Backend/schemas`, ADR-0004 | ProjectSpec, BuildState, RunEvent, IntakeResult. Generates Pydantic models, TS types and the API client from OpenAPI. `make codegen-check` fails on stale output |
| Database | `Backend/db`, ADR-0005 | 12 PRD tables + `idempotency_keys`; append-only and immutable triggers; LangGraph tables in `langgraph` schema |
| Auth | ADR-0006 | Clerk JWT (JWKS, iss/azp), JIT provisioning, Svix-verified webhooks, personal org on sign-up, platform role from Clerk `public_metadata.role` (audited) |
| API | `Backend/api` | projects, runs, SSE events (Last-Event-ID), spec approval, uploads/downloads (signed, 10 min), admin lists, idempotency keys, cursor paging |
| LLM gateway | `Backend/llm`, ADR-0007, ADR-0013 | Gemini (primary) + Anthropic + OpenAI + fake adapters, role routing in YAML, fallback on 429/5xx/timeouts, per-call cost logging |
| Sandbox | `Backend/engines_runner`, ADR-0008 | local Docker (nobody, read-only, no caps, limits, timeout, no network by default, egress allowlist proxy) + E2B stub; stale-sandbox reaper |
| Engines | `Backend/engines` | Engine contract, echo engine, interface stubs for all 13 PRD engines |
| Run pipeline | `Backend/agents`, ADR-0009 | LangGraph intake -> spec -> approval gate -> version -> echo in sandbox -> finish; Postgres checkpointer; Redis lease + recovery cron |
| Frontend | `Frontend/` | pnpm workspace; studio (sign-in, project list, prompt box, 3-panel studio, live build log, approve spec); admin console; Astro site |
| Observability | | JSON logs with request/run ids, Sentry (FE + BE) when DSN set, LangSmith when key set |

## Verified so far

Phase 0 baseline (2026-10-30); current numbers are in `docs/phase-0-report.md`.

- Backend: 113 tests pass (unit and integration against real Postgres, Redis, S3 and Docker),
  including the pipeline crash-resume test.
- Frontend: lint, typecheck and unit tests pass; studio, admin and site production builds succeed.
- `make dev`: all 13 containers come up healthy from the compose file.
- **Restart gate (system level): passes.** `Backend/tests/system/test_compose_restart.py` kills
  the worker container mid-engine, restarts it, and the run finishes exactly once (no duplicate
  seqs, one version, one artifact).

## What is left to close Phase 0

1. ~~Add the Clerk values as GitHub repo secrets.~~ Done; CI passes `make check` on GitHub.
2. ~~Write the Phase 0 completion report.~~ Done: `docs/phase-0-report.md`.

Clerk dev instance (2026-10-31): Consumer app "Kehora", email + password sign-in, bot sign-up
protection off, test user `e2e+clerk_test@example.com`. Keys are in `.env` only.

## Phase 1 started early (owner-approved, 2026-10-30)

Backend Phase 1 work started before the Phase 0 Playwright gate ran, because that gate is
blocked only on Clerk keys. Engine work needs no sign-in. Anything user-facing ships behind a
feature flag until both gates pass.

- CAD engine: build123d in sandbox image `kehora/engine-cad`, verifier (ADR-0010).
- Printability engine: bed fit, overhangs, walls, orientation, one-click fixes; printer and
  material profiles in `Backend/data` (ADR-0011).
- Objects eval suite: 100 cases, scorer, runner with `reference` and `agent` builders, 11
  reference solutions.
- Mechanical agent: design loop with up to 5 repairs, `mechanical` graph node behind
  `FEATURE_PHASE1_OBJECTS` (ADR-0012).

Downloads finished on 2026-10-31 (CAD image `kehora/engine-cad:0.13.0`, 1.8 GB; numpy and
trimesh dev deps). Verified then: `make check-backend` passes (187 tests, including every
sandbox test), `make check-frontend` passes, `make codegen-check` is up to date, and
`python -m evals objects --builder reference` passes 11 of 11 built cases.

Fixed during verification: a result with no solid (faces only) is now reported as
"contains no solid" before export instead of a 3MF exporter crash.

Still to do in Phase 1: agent eval runs on Gemini (`GEMINI_API_KEY` is set; every role is on
`gemini-3.8-flash` until billing is enabled, then design moves to `gemini-4-argon`), slicing
engine, studio 3D viewer and parameters panel.

## Decisions waiting for your review

- OpenAI fallback models (`gpt-5.5`, `gpt-5.4-mini`) and their prices (left blank) in
  `Backend/llm/kehora_llm/config/`.
- Gemini is now the primary provider (ADR-0013). Update `pricing.yaml` on 2026-12-01
  (gemini-4-argon) and 2027-01-01 (gemini-3.8-flash), when Google's prices rise.
- Run cost stored as USD cents rounded up, with micro-dollar detail per call (ADR-0007).
- Columns added beyond PRD 9 (ADR-0005): `users.role`, `users.deleted_at`,
  `organizations.clerk_org_id`, `agent_runs.org_id/created_by_id/cost_currency/error`,
  `run_events.node`, artifact type `log`.
- `Backend/common` is an extra folder not in CLAUDE.md's layout (ADR-0003); update CLAUDE.md if
  accepted.
- ADR-0010: CAD script contract (`result` variable, mm) and bounding-box-only dimension check.
- ADR-0011: printability thresholds (1% thin-wall area, 25 mm² overhang, 50 mm² bed contact).
- ADR-0012: `mechanical` role on the strongest model tier; repairs on the cheaper `repair` tier.
- The git author is set repo-locally to "Emma" with your email; change it if wrong.

## Known follow-ups (not Phase 0 blockers)

- **Playwright flake, not reproduced:** on the first `make e2e` against a freshly built stack,
  `run-resume` timed out because `POST /v1/projects` reached the API and never answered (no
  error logged; health checks kept passing). Three later runs passed. If it recurs, capture
  `docker compose logs api` and a Postgres `pg_stat_activity` snapshot during the hang.
- With the offline `test` LLM profile the fake spec writer echoes the prompt as the title
  ("Category from intake: object Request: ..."). Cosmetic, test profile only.

- Studio bundle is about 610 kB; code-split before targeting the 1 Mbps NFR.
- Frontend containers have no hot reload (Linux `node_modules` are built into the image); use
  `pnpm dev` on the host for HMR.
- The local egress filter is global, not per job; the hosted sandbox must enforce per job.
- Upload scanning/re-encoding, rate limits and credit checks are later-phase work (credits sit
  behind `FEATURE_CREDITS_ENFORCED`).
- OpenTelemetry is not wired yet.
- The studio 3D viewer fetches STLs straight from signed S3 URLs. Local SeaweedFS allows
  cross-origin reads by default; production S3 needs a bucket CORS rule allowing `GET` from the
  studio origin (add it in Terraform with the bucket).

## How to resume

```
cp .env.example .env    # then fill the Clerk values
make dev                # studio :5173, admin :5174, site :4321, api :8000/docs
make check              # full gate, including make e2e
```
