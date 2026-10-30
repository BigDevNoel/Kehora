# ADR-0009: Run pipeline, events, approvals and crash recovery

- Status: accepted (approved in the Phase 0 plan; recovery mechanics added here)
- Date: 2026-10-30

## Context

Phase 0 gate: a run streams events end to end, pauses at the spec approval gate, resumes on
approval, and survives killing the worker mid-run. PRD 6: the Postgres checkpointer saves state
after every node; PRD 10: SSE resumable with `Last-Event-ID`.

## Decision

**Events.** `emit()` takes a row lock on the run, assigns `seq = max(seq) + 1`, inserts into
`run_events` and commits; then it XADDs to the Redis stream `run:{id}:events` with entry id
`{seq}-0`. Postgres is the source of truth; the stream is the live feed. SSE: replay rows with
`seq > Last-Event-ID` from Postgres, then XREAD from `{last}-0`; if a gap appears (an XADD was
lost in a crash) or a read times out, backfill from Postgres. The stream closes after
`run_finished` / `run_failed`.

**Graph.** intake -> spec -> request_spec_approval -> spec_gate -> create_version -> engine ->
finish. The gate is two nodes because LangGraph re-runs an interrupted node from the top on
resume: `request_spec_approval` writes the pending `approvals` row and emits `needs_approval`
once; `spec_gate` only calls `interrupt()`. State is `BuildState`; nodes return JSON-only
updates so checkpoints contain no custom classes. Side effects are idempotent (version created
once per run, artifact keyed by deterministic S3 key).

**One job, derived from state.** The API never passes decisions through the queue. It writes the
decision to `approvals`, commits, and enqueues `execute_run(run_id)`. The worker works out what
to do from the checkpoint and `approvals`: start, continue, resume with the stored decision, or
nothing. Any number of duplicate jobs is harmless.

**Single executor.** A Redis lease `run:{id}:lease` (SET NX, 10 s TTL, refreshed every 3 s)
guards execution. A job that finds the lease held retries in 2 s, so a decision stored while
another worker is busy is still applied.

**Crash recovery.** On startup and every 5 s the worker re-enqueues runs that are
`queued`/`running` with no live lease and no update for 15 s, and runs paused at a gate whose
decision is stored. LangGraph then continues from the last checkpoint; the interrupted node runs
again (it emits a second `node_started`, which the build log shows as a restart).

**Outcomes.** Policy refusal at intake and a rejected spec end the run as `cancelled` with
`run_failed`. A failing verifier ends it as `failed`; `run_finished` is only emitted after every
check passed.

## Consequences

- Worst-case resume latency after a worker death is about 15 to 20 seconds.
- A run's events are totally ordered per run; there is no ordering across runs.
