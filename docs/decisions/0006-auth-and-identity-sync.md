# ADR-0006: Clerk authentication and identity sync

- Status: accepted
- Date: 2026-10-30

## Context

CLAUDE.md fixes Clerk for auth; PRD 10 puts a Clerk JWT in the `Authorization` header and PRD 9
syncs users from Clerk webhooks. Open points: how tokens are verified, what happens before the
first webhook arrives, where the platform (admin) role comes from, and how orgs map.

## Decision

**Token verification.** RS256 only; keys from `<CLERK_ISSUER>/.well-known/jwks.json`, cached by
`kid`, refetched on an unknown `kid` at most once a minute. Required claims `exp`, `iat`, `sub`,
`iss`; `iss` must equal `CLERK_ISSUER`; `azp`, when present, must be in
`CLERK_AUTHORIZED_PARTIES`; 5 s clock leeway. The active org comes from `o.id` (session token
v2) or `org_id` (v1).

**Just-in-time provisioning.** Clerk webhooks cannot reach `localhost` without a tunnel, and in
production the first API call can beat the `user.created` webhook. When a valid token's `sub` has
no `users` row, the API fetches the user from the Clerk Backend API and runs the same upsert the
webhook uses. Every write is an `INSERT ... ON CONFLICT` keyed on the Clerk id, so the race and
Svix retries are harmless.

**Personal org.** A new user gets an `organizations` row (`type=personal`) and an `owner`
membership. Clerk organizations sync as `type=business`; Clerk roles map `org:owner|admin|member|
viewer` to our roles, unknown roles to `member`.

**Platform role.** `users.role` (`user|support|admin`) is read only from Clerk
`public_metadata.role`, which users cannot write themselves (only the Clerk dashboard or our
backend can). Unknown values fall back to `user`. Every change is written to `audit_log`.
To make someone staff: Clerk dashboard → user → Metadata → Public → `{"role": "admin"}`.

**Deletes.** `user.deleted` sets `users.deleted_at`; such users get 401. `organization.deleted`
removes memberships but keeps the org row (projects reference it).

**Webhooks.** `POST /v1/webhooks/clerk` verifies the Svix signature on the raw body before
parsing; a bad signature is 400 and writes nothing.

## Consequences

- `make dev` works with only Clerk keys in `.env`; webhooks are optional locally.
- Org membership changes made in Clerk need the webhook to reach us (use a tunnel such as
  `ngrok` or the Clerk dashboard's "send test event" to try them locally).
- Authorization errors on org resources return 404, not 403, so ids are not probeable.
