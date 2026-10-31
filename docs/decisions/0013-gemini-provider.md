# ADR-0013: Gemini as the primary model provider

- Status: accepted (owner chose Gemini, 2026-10-31)
- Date: 2026-10-31

## Context

The gateway (ADR-0007) shipped with Anthropic primary and OpenAI fallback. The owner chose
Google Gemini. CLAUDE.md requires model access to stay provider-agnostic, with provider SDKs
only in `Backend/llm/`.

## Decision

- **Adapter** `kehora_llm/adapters/gemini_adapter.py` on the official `google-genai` SDK
  (2.31.0, Gemini Developer API with `GEMINI_API_KEY`). Structured output via
  `response_json_schema`; tools as function declarations; `effort` maps to `thinking_level`
  (low/medium, and HIGH for high and above). Thought parts are never returned as answer text;
  thinking tokens count as output for cost. 429 and 5xx fall back; other 4xx fail loudly;
  blocked prompts or answers raise `RefusalError`.
- **Routing (default profile):** Gemini first for every role, `gemini-4-argon` for spec,
  planner, mechanical and vision, `gemini-3.8-flash` for intake and repair. Anthropic and
  OpenAI stay in each chain as fallbacks; a provider without a key is skipped.
- **Prices** from ai.google.dev/gemini-api/docs/pricing (read 2026-10-31). Scheduled rises are
  noted in `pricing.yaml`: gemini-4-argon on 2026-12-01, gemini-3.8-flash on 2027-01-01.
- The architecture test now also catches `from google import genai` outside `Backend/llm/`.

## Consequences

- `make evals` must be run on Gemini before relying on its pass rate (rule 9); compare with
  another provider if results disappoint. Switching back is a `routing.yaml` change.
- Cost logging is wrong after the scheduled price dates unless `pricing.yaml` is updated.
- Vertex AI (service accounts, regional endpoints) is not wired; only the API-key path.
