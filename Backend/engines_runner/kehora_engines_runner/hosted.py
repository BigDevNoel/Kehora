"""Hosted sandbox provider (E2B first, per CLAUDE.md). Stub until the provider is chosen and
integrated; selecting it fails loudly instead of silently running code elsewhere."""

from kehora_engines.base import SandboxJob, SandboxResult


class E2BSandbox:
    name = "e2b"

    def __init__(self, api_key: str | None) -> None:
        self._api_key = api_key

    async def run(self, job: SandboxJob) -> SandboxResult:
        raise NotImplementedError(
            "E2B sandbox provider is not implemented yet; use SANDBOX_PROVIDER=local_docker"
        )
