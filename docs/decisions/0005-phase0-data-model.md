# ADR-0005: Phase 0 data model details and additions to PRD section 9

- Status: accepted (additions approved in the Phase 0 plan; column-level details below)
- Date: 2026-10-30

## Context

PRD section 9 lists tables and key fields but leaves types, enums, constraints and a few
operational columns open. Phase 0 creates: users, organizations, memberships, projects,
project_versions, artifacts, agent_runs, run_events, checks, approvals, credit_ledger,
audit_log.

## Decision

Conventions for every table: `id uuid` primary key generated app-side as UUID v7
(`kehora_common.ids.new_id`), `created_at` / `updated_at` as `timestamptz` (UTC, DB default
`now()`). Enums are stored as `text` with a `CHECK` constraint (not native PG enums) so adding a
value is a one-line migration.

Additions beyond PRD section 9:

| Table | Addition | Why |
| --- | --- | --- |
| users | `role text` in `user, support, admin`, default `user` | Platform role; gates `/v1/admin/*`. Org roles stay in memberships. |
| users | `deleted_at timestamptz null` | Clerk `user.deleted` soft-deletes; hard delete job comes with the GDPR/NDPA work. |
| organizations | `clerk_org_id text unique null` | Null = personal org created on `user.created`. |
| projects | `visibility` in `private, unlisted, public`, default `private` | PRD names the column, not the values. |
| projects | `kind` nullable | Unknown until intake classifies the prompt. |
| agent_runs | `cost_currency char(3)` default `USD` | Rule 6: money is minor units plus a currency. |
| agent_runs | `org_id`, `created_by_id` | Permission checks and credit/billing attribution without joins through projects. |
| agent_runs | `error text null` | Human-readable failure reason for the build log and admin. |
| run_events | `node text null` | Matches RunEvent schema; which graph node emitted it. |
| approvals | `status` in `pending, approved, rejected` | PRD names gate and status, not values. Spec edits come later. |
| artifacts | type value `log` | Phase 0 echo engine output; also used later for build logs. |
| idempotency_keys | new table | PRD 10 requires `Idempotency-Key` on mutating endpoints. Unique per (user_id, key); stores request hash and the replayed response; 24 h expiry. |

Integrity rules enforced in the database, not only in code:

- `run_events`, `credit_ledger`, `audit_log`: append-only. A trigger rejects UPDATE and DELETE.
- `project_versions`: immutable once created. A trigger rejects UPDATE.
- `run_events (run_id, seq)` and `project_versions (project_id, number)` are unique.
- `credit_ledger.delta` and `balance_after` are integer credits (not money). Credits are not
  enforced in Phase 0 (flag `credits_enforced`).

LangGraph checkpoint tables live in the `langgraph` schema, created by the checkpointer's
own `setup()`. Alembic manages only the `public` schema.

## Consequences

Changing any of these is a migration plus an ADR update. Payments-related tables (orders,
payments, escrow, payouts) are deliberately absent until Phase 4.
