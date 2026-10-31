"""Mesh + printer profile + material -> walls, overhangs, bed fit and orientation report.

PRD 7 and 8.2, ADR-0011. `analysis.py` and `harness.py` run in the CAD sandbox image; this
module only builds the job, validates the report against the `PrintabilityReport` schema and
turns it into checks. Bridges and support volume come from the slicer, not from here.
"""

import json
from importlib.resources import files as package_files
from typing import ClassVar

from pydantic import BaseModel, Field, ValidationError, model_validator

from kehora_engines.base import Engine, EngineError, SandboxJob, SandboxLimits, SandboxResult
from kehora_engines.cad import IMAGE
from kehora_schemas import CheckResult, CheckStatus, Material, PrintabilityReport, PrinterProfile

MAX_STL_BYTES = 200 * 1024 * 1024
LOAD_ERROR_EXIT = 3


class PrintabilityInput(BaseModel):
    stl: bytes = Field(min_length=84, max_length=MAX_STL_BYTES, repr=False)
    printer: PrinterProfile
    material: Material
    samples: int = Field(default=800, ge=50, le=5000, description="Wall-thickness rays.")
    seed: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _same_technology(self) -> "PrintabilityInput":
        if self.printer.technology != self.material.technology:
            raise ValueError(f"{self.material.name} cannot be printed on {self.printer.name}")
        return self


class PrintabilityOutput(BaseModel):
    report: PrintabilityReport | None = None
    load_error: str | None = None


def _file(name: str) -> bytes:
    return package_files("kehora_engines.printability").joinpath(name).read_bytes()


class PrintabilityEngine(Engine[PrintabilityInput, PrintabilityOutput]):
    name: ClassVar[str] = "printability"
    phase: ClassVar[int] = 1

    def build_job(self, inp: PrintabilityInput) -> SandboxJob:
        params = {
            "printer": inp.printer.model_dump(mode="json"),
            "material": inp.material.model_dump(mode="json"),
            "samples": inp.samples,
            "seed": inp.seed,
        }
        return SandboxJob(
            image=IMAGE,
            command=["python", "/work/in/harness.py"],
            files={
                "harness.py": _file("harness.py"),
                "analysis.py": _file("analysis.py"),
                "part.stl": inp.stl,
                "params.json": json.dumps(params).encode(),
            },
            limits=SandboxLimits(cpus=2, memory_mb=2048, pids=128, timeout_s=300),
        )

    def parse(self, inp: PrintabilityInput, result: SandboxResult) -> PrintabilityOutput:
        if result.exit_code == LOAD_ERROR_EXIT and "load_error.txt" in result.outputs:
            return PrintabilityOutput(load_error=result.outputs["load_error.txt"].decode()[:2000])
        raw = result.outputs.get("report.json")
        if result.exit_code != 0 or raw is None:
            raise EngineError(
                f"printability harness failed (exit {result.exit_code}): {result.stderr[-500:]}"
            )
        try:
            return PrintabilityOutput(report=PrintabilityReport.model_validate_json(raw))
        except ValidationError as e:
            raise EngineError(f"printability harness wrote an invalid report: {e}") from e

    def verify(self, inp: PrintabilityInput, out: PrintabilityOutput) -> list[CheckResult]:
        """One `printable` check: fail on any blocking issue, warn on warnings (PRD 7)."""
        if out.report is None:
            return [
                CheckResult(
                    engine=self.name,
                    name="mesh_loads",
                    status=CheckStatus.fail,
                    report={"error": out.load_error},
                )
            ]
        report = out.report
        if report.blocking:
            status = CheckStatus.fail
        elif report.issues:
            status = CheckStatus.warn
        else:
            status = CheckStatus.pass_
        return [
            CheckResult(
                engine=self.name,
                name="printable",
                status=status,
                report=report.model_dump(mode="json"),
            )
        ]
