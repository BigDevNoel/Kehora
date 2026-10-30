"""SandboxProvider: where agent-generated and engine code runs (CLAUDE.md rule 4, ADR-0008).

Guarantees every provider must give: no network unless the job lists allowed hosts, CPU /
memory / process limits, a hard timeout (10 minutes max), no secrets inside the sandbox, and
the sandbox destroyed after each job.
"""

from typing import Protocol

from kehora_engines.base import SandboxJob, SandboxResult


class SandboxError(Exception):
    """The sandbox itself failed (could not start, provider error). Not an engine failure."""


class SandboxPolicyError(SandboxError):
    """The job asked for something the policy forbids (e.g. a host outside the allowlist)."""


class SandboxProvider(Protocol):
    name: str

    async def run(self, job: SandboxJob) -> SandboxResult: ...


def check_allowlist(job: SandboxJob, permitted: set[str]) -> None:
    extra = set(job.network_allowlist) - permitted
    if extra:
        raise SandboxPolicyError(f"hosts not in the sandbox egress allowlist: {sorted(extra)}")


SECRET_ENV_MARKERS = ("KEY", "SECRET", "TOKEN", "PASSWORD", "DSN", "CREDENTIAL")


def check_no_secrets(job: SandboxJob) -> None:
    """Secrets never enter sandboxes (CLAUDE.md rule 12). Reject suspicious env names."""
    bad = [k for k in job.env if any(m in k.upper() for m in SECRET_ENV_MARKERS)]
    if bad:
        raise SandboxPolicyError(f"secret-like env vars are not allowed in sandboxes: {bad}")
