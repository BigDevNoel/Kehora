"""Engine contract (CLAUDE.md rule 2, PRD 7).

An engine is pure: typed input -> a sandbox job description -> typed output -> its own verifier.
Engines never call LLMs or the network; the runner executes the job inside a SandboxProvider.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, Field

from kehora_schemas import CheckResult

DEFAULT_TIMEOUT_S = 600  # PRD 11: 10-minute sandbox timeout


class SandboxLimits(BaseModel):
    cpus: float = Field(default=1.0, gt=0, le=8)
    memory_mb: int = Field(default=1024, ge=64, le=16384)
    pids: int = Field(default=256, ge=16, le=4096)
    timeout_s: int = Field(default=DEFAULT_TIMEOUT_S, ge=1, le=DEFAULT_TIMEOUT_S)


class SandboxJob(BaseModel):
    """Everything a sandbox needs. Inputs land in /work/in; the job writes to /work/out."""

    image: str
    command: list[str]
    files: dict[str, bytes] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict, description="Non-secret config only.")
    limits: SandboxLimits = Field(default_factory=SandboxLimits)
    network_allowlist: list[str] = Field(
        default_factory=list, description="Hostnames the job may reach. Empty = no network."
    )


class SandboxResult(BaseModel):
    exit_code: int
    stdout: str
    stderr: str
    outputs: dict[str, bytes]
    timed_out: bool = False
    duration_ms: int = 0


class EngineError(Exception):
    """The sandbox ran but the engine's output could not be parsed."""


class Engine[I: BaseModel, O: BaseModel](ABC):
    name: ClassVar[str]
    phase: ClassVar[int]

    @abstractmethod
    def build_job(self, inp: I) -> SandboxJob: ...

    @abstractmethod
    def parse(self, inp: I, result: SandboxResult) -> O: ...

    @abstractmethod
    def verify(self, inp: I, out: O) -> list[CheckResult]: ...


class NotYetImplementedEngine[I: BaseModel, O: BaseModel](Engine[I, O]):
    """Interface-only stub for engines that land in later phases."""

    def build_job(self, inp: I) -> SandboxJob:
        raise NotImplementedError(f"{self.name} engine ships in phase {self.phase}")

    def parse(self, inp: I, result: SandboxResult) -> O:
        raise NotImplementedError(f"{self.name} engine ships in phase {self.phase}")

    def verify(self, inp: I, out: O) -> list[CheckResult]:
        raise NotImplementedError(f"{self.name} engine ships in phase {self.phase}")
