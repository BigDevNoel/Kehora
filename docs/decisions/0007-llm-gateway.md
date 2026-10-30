# ADR-0007: LLM gateway design

- Status: accepted (approved in the Phase 0 plan; cost units and OpenAI model choice need review)
- Date: 2026-10-30

## Context

PRD 6: one model-agnostic interface (`complete`, `stream`, `structured`, `tool_call`, `vision`),
adapters per provider, a role -> model routing table in config, automatic fallback to a second
provider, and token/cost logging per run, user and project. CLAUDE.md rule 3: no LLM SDK imports
outside `Backend/llm/` (enforced by `tests/test_architecture.py`).

## Decision

- **Adapters:** `anthropic` (official SDK, Messages API), `openai` (official SDK, Chat
  Completions) and `fake` (deterministic, offline). Agents use only `kehora_llm.types`.
- **Routing:** `kehora_llm/config/routing.yaml`, profile chosen by `LLM_ROUTING_PROFILE`.
  `default`: spec/planner/vision -> `claude-opus-5-5`, repair -> `claude-sonnet-5-5`,
  intake -> `claude-haiku-5-5`, each with an OpenAI fallback. `test`: every role -> `fake`.
- **Fallback:** on timeout, connection error, 429, 5xx/529 the next model in the chain is tried.
  4xx (bad request, auth) fails immediately: it's a bug, not an outage. Streams fall back only
  before the first token. Refusals are not retried on another provider (policy decision).
- **Anthropic specifics:** thinking left at the adaptive default; depth set via `effort`.
  Server-side refusal fallback (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`)
  is on for Opus 5.5 / Sonnet 5.5. Forced `tool_choice` is not used (rejected by current models).
  Structured output uses `output_config.format` with `anthropic.transform_schema`; the gateway
  then validates against the Pydantic model and raises `OutputValidationError` on mismatch.
- **Cost logging:** each call yields a `UsageRecord` (role, provider, served model, tokens,
  `cost_usd_micros`, latency, fallback_from) passed to a caller-supplied sink. The run worker
  appends records to `agent_runs.model_usage` and sets `agent_runs.cost_minor` to the total in
  **USD cents, rounded up** (`cost_currency = USD`), and emits `cost_update`.
  Rationale: a single call often costs a fraction of a cent, so per-call precision is kept in
  micros inside `model_usage`; the money column stays in ISO minor units (rule 6).
  Prices live in `config/pricing.yaml`; a model without a price logs `cost: null` + a warning.

## Open items for review

- OpenAI fallback models (`gpt-5.5`, `gpt-5.4-mini`) were picked from the SDK's model list,
  and their prices are deliberately not filled in. Confirm both before relying on fallback cost
  numbers.
- Credits are not charged from these costs yet (flag `credits_enforced`, Phase 1 pricing work).
