# ADR-0008: SandboxProvider and the local Docker sandbox

- Status: accepted (approved in the Phase 0 plan)
- Date: 2026-10-30

## Context

CLAUDE.md rule 4 and PRD 11: agent-written and engine code runs only in sandboxes, with no
network except an allowlist, CPU and memory limits, a 10-minute timeout, no secrets, and the
sandbox destroyed after each job. E2B or Modal is the first hosted provider.

## Decision

- `SandboxProvider.run(SandboxJob) -> SandboxResult` (`Backend/engines_runner`). A job is pure
  data from an engine: image, command, input files (`/work/in`), non-secret env, limits, and
  an optional host allowlist. Outputs come back from `/work/out` as bytes; the caller stores
  them in S3. Engines (`Backend/engines`) never touch Docker, S3 or the network.
- **Policy checks before any provider runs a job:** env names that look like secrets
  (`KEY`, `SECRET`, `TOKEN`, ...) are rejected; requested hosts must be in the global allowlist
  (`runner.EGRESS_ALLOWLIST`, mirrored in `infra/docker/egress/filter`).
- **LocalDockerSandbox (dev/CI only):** per-job scratch volume, container as `nobody`,
  read-only rootfs, `cap_drop=ALL`, `no-new-privileges`, `--cpus/--memory/--pids-limit`,
  64 MB noexec `/tmp`, `network_mode=none` by default. A job with an allowlist joins the
  `kehora-sandbox` internal network whose only way out is the tinyproxy `egress` service
  (default deny, domain filter). Timeout -> kill (exit 137). Containers and volume are removed
  in `finally`. Tests verify each property against a real Docker engine.
- **E2BSandbox:** stub that raises; selecting it fails loudly.

## Consequences

- The worker container mounts the Docker socket, which is root-equivalent on the host. This is
  acceptable for local dev and CI only; production must use the hosted provider.
- The local egress filter is global, not per job: a job can reach any globally allowlisted host
  once it asks for network at all. The hosted provider must enforce per-job allowlists.
