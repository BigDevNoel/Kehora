"""Run an engine inside a sandbox and verify its output."""

from dataclasses import dataclass

from pydantic import BaseModel

from kehora_common.settings import Settings
from kehora_engines.base import Engine, SandboxResult
from kehora_engines_runner.hosted import E2BSandbox
from kehora_engines_runner.local_docker import LocalDockerSandbox
from kehora_engines_runner.sandbox import SandboxProvider
from kehora_schemas import CheckResult

# Hosts a sandbox may ever reach (PRD 11: package mirrors, parts APIs). Jobs request a subset.
EGRESS_ALLOWLIST = {"pypi.org", "files.pythonhosted.org", "registry.npmjs.org"}


@dataclass(frozen=True)
class EngineRun[O: BaseModel]:
    output: O
    checks: list[CheckResult]
    result: SandboxResult


async def run_engine[I: BaseModel, O: BaseModel](
    provider: SandboxProvider, engine: Engine[I, O], inp: I
) -> EngineRun[O]:
    result = await provider.run(engine.build_job(inp))
    output = engine.parse(inp, result)
    return EngineRun(output=output, checks=engine.verify(inp, output), result=result)


def build_sandbox(settings: Settings) -> SandboxProvider:
    if settings.sandbox_provider == "e2b":
        key = settings.e2b_api_key.get_secret_value() if settings.e2b_api_key else None
        return E2BSandbox(key)
    return LocalDockerSandbox(
        egress_proxy=settings.sandbox_egress_proxy, egress_allowlist=EGRESS_ALLOWLIST
    )
