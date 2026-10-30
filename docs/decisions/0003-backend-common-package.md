# ADR-0003: `Backend/common` shared package

- Status: accepted (approved in the Phase 0 plan)
- Date: 2026-10-30

## Context

CLAUDE.md lists the Backend folders but has no home for code every service needs: settings,
structured logging, UUID v7 generation, UTC clock, feature flags and the S3 client. Putting
these in `api/` would make workers depend on the API package; putting them in `llm/` would
blur the provider-isolation rule.

## Decision

Add one extra uv workspace member, `Backend/common` (`kehora-common`, import `kehora_common`).
It depends on nothing else in the workspace, holds no business logic, and imports no LLM or
payment SDKs. All Backend Python packages use the `kehora_` import prefix and `kehora-` dist
prefix (`kehora_api`, `kehora_llm`, ...), so generic names like `api` or `db` never shadow
third-party packages.

## Consequences

- One extra folder beyond the CLAUDE.md layout. CLAUDE.md's repo layout should list it; update
  CLAUDE.md when this ADR is accepted.
- `common` must stay small. Anything with domain meaning belongs in its owning package.
