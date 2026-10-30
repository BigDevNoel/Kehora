"""Phase 0 echo engine: proves the sandbox path end to end (inputs in, outputs out, verifier)."""

import hashlib
from typing import ClassVar

from pydantic import BaseModel, Field

from kehora_engines.base import Engine, EngineError, SandboxJob, SandboxLimits, SandboxResult
from kehora_schemas import CheckResult, CheckStatus

IMAGE = "busybox:1.37.0"


class EchoInput(BaseModel):
    message: str = Field(min_length=1, max_length=10_000)


class EchoOutput(BaseModel):
    text: str
    sha256: str


class EchoEngine(Engine[EchoInput, EchoOutput]):
    name: ClassVar[str] = "echo"
    phase: ClassVar[int] = 0

    def build_job(self, inp: EchoInput) -> SandboxJob:
        return SandboxJob(
            image=IMAGE,
            command=["sh", "-c", "cp /work/in/message.txt /work/out/echo.txt && echo done"],
            files={"message.txt": inp.message.encode()},
            limits=SandboxLimits(cpus=0.5, memory_mb=64, pids=32, timeout_s=60),
        )

    def parse(self, inp: EchoInput, result: SandboxResult) -> EchoOutput:
        if result.exit_code != 0 or "echo.txt" not in result.outputs:
            raise EngineError(f"echo failed (exit {result.exit_code}): {result.stderr[-500:]}")
        data = result.outputs["echo.txt"]
        return EchoOutput(text=data.decode(), sha256=hashlib.sha256(data).hexdigest())

    def verify(self, inp: EchoInput, out: EchoOutput) -> list[CheckResult]:
        same = out.text == inp.message
        return [
            CheckResult(
                engine=self.name,
                name="round_trip",
                status=CheckStatus.pass_ if same else CheckStatus.fail,
                report={"expected_bytes": len(inp.message.encode()), "got_bytes": len(out.text)},
            )
        ]
