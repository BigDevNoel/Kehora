"""Mechanical code-CAD: build123d script -> STEP, STL, 3MF and measurements (PRD 7, ADR-0010).

The script runs in the CAD sandbox image through `harness.py`. The verifier checks that the
script ran, the solid is valid and watertight, and the bounding box is within tolerance of the
spec. Renders come from the render engine later in phase 1.
"""

import json
from importlib.resources import files as package_files
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, ValidationError

from kehora_engines.base import Engine, EngineError, SandboxJob, SandboxLimits, SandboxResult
from kehora_schemas import CheckResult, CheckStatus

IMAGE = "kehora/engine-cad:0.13.0"
EXPORTS = ("part.step", "part.stl", "part.3mf")
DEFAULT_TOLERANCE_MM = 0.1  # PRD 7: dimensions within ±0.1 mm of spec
MAX_SCRIPT_BYTES = 200_000


class ExpectedSize(BaseModel):
    """Bounding-box size the spec asks for. Unset axes are not checked."""

    x: float | None = Field(default=None, gt=0)
    y: float | None = Field(default=None, gt=0)
    z: float | None = Field(default=None, gt=0)


class CadInput(BaseModel):
    script: str = Field(min_length=1, max_length=MAX_SCRIPT_BYTES)
    expected_size_mm: ExpectedSize | None = None
    tolerance_mm: float = Field(default=DEFAULT_TOLERANCE_MM, gt=0, le=5)
    linear_tolerance_mm: float = Field(default=0.01, gt=0, le=1, description="STL/3MF chord.")
    angular_tolerance_rad: float = Field(default=0.1, gt=0, le=1)


class BrepReport(BaseModel):
    is_valid: bool
    solid_count: int
    volume_mm3: float
    area_mm2: float
    bbox_min_mm: tuple[float, float, float]
    bbox_max_mm: tuple[float, float, float]

    @property
    def size_mm(self) -> tuple[float, float, float]:
        lo, hi = self.bbox_min_mm, self.bbox_max_mm
        return (hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2])


class MeshReport(BaseModel):
    triangles: int
    is_watertight: bool
    is_winding_consistent: bool
    volume_mm3: float


class CadReport(BaseModel):
    """report.json written by the harness."""

    ok: bool
    stage: Literal["script", "result", "export"] | None = None
    error: str | None = None
    brep: BrepReport | None = None
    mesh: MeshReport | None = None


class CadOutput(BaseModel):
    report: CadReport
    files: dict[str, bytes] = Field(default_factory=dict, repr=False)


def _harness() -> bytes:
    return package_files("kehora_engines.cad").joinpath("harness.py").read_bytes()


class CadEngine(Engine[CadInput, CadOutput]):
    name: ClassVar[str] = "cad"
    phase: ClassVar[int] = 1

    def build_job(self, inp: CadInput) -> SandboxJob:
        params = {
            "linear_tolerance_mm": inp.linear_tolerance_mm,
            "angular_tolerance_rad": inp.angular_tolerance_rad,
        }
        return SandboxJob(
            image=IMAGE,
            command=["python", "/work/in/harness.py"],
            files={
                "harness.py": _harness(),
                "script.py": inp.script.encode(),
                "params.json": json.dumps(params).encode(),
            },
            limits=SandboxLimits(cpus=2, memory_mb=2048, pids=256, timeout_s=300),
        )

    def parse(self, inp: CadInput, result: SandboxResult) -> CadOutput:
        if result.timed_out:
            report = CadReport(ok=False, stage="script", error="the script timed out")
            return CadOutput(report=report)
        raw = result.outputs.get("report.json")
        if result.exit_code != 0 or raw is None:
            raise EngineError(
                f"cad harness failed (exit {result.exit_code}): {result.stderr[-500:]}"
            )
        try:
            report = CadReport.model_validate_json(raw)
        except ValidationError as e:
            raise EngineError(f"cad harness wrote an invalid report: {e}") from e
        if report.ok and any(name not in result.outputs for name in EXPORTS):
            raise EngineError("cad harness reported success but an export is missing")
        exports = {name: result.outputs[name] for name in EXPORTS if name in result.outputs}
        return CadOutput(report=report, files=exports)

    def verify(self, inp: CadInput, out: CadOutput) -> list[CheckResult]:
        report = out.report
        if not report.ok or report.brep is None or report.mesh is None:
            return [
                self._check(
                    "script_runs",
                    CheckStatus.fail,
                    {"stage": report.stage, "error": report.error},
                )
            ]
        brep, mesh = report.brep, report.mesh
        checks = [
            self._check("script_runs", CheckStatus.pass_, {}),
            self._check(
                "solid_valid",
                _status(brep.is_valid and brep.solid_count >= 1 and brep.volume_mm3 > 0),
                {
                    "is_valid": brep.is_valid,
                    "solid_count": brep.solid_count,
                    "volume_mm3": brep.volume_mm3,
                },
            ),
            self._check(
                "watertight",
                _status(mesh.is_watertight and mesh.is_winding_consistent),
                mesh.model_dump(),
            ),
        ]
        if brep.solid_count > 1:
            checks.append(
                self._check(
                    "single_body",
                    CheckStatus.warn,
                    {"solid_count": brep.solid_count, "hint": "separate bodies print as parts"},
                )
            )
        if inp.expected_size_mm is not None:
            checks.append(self._dimensions(inp, inp.expected_size_mm, brep))
        return checks

    def _dimensions(self, inp: CadInput, expected: ExpectedSize, brep: BrepReport) -> CheckResult:
        got = dict(zip("xyz", brep.size_mm, strict=True))
        axes = {}
        for axis, want in expected.model_dump().items():
            if want is None:
                continue
            delta = got[axis] - want
            axes[axis] = {
                "expected_mm": want,
                "actual_mm": round(got[axis], 4),
                "delta_mm": round(delta, 4),
                "ok": abs(delta) <= inp.tolerance_mm,
            }
        ok = all(a["ok"] for a in axes.values())
        return self._check(
            "dimensions", _status(ok), {"tolerance_mm": inp.tolerance_mm, "axes": axes}
        )

    def _check(self, name: str, status: CheckStatus, report: dict[str, object]) -> CheckResult:
        return CheckResult(engine=self.name, name=name, status=status, report=report)


def _status(ok: bool) -> CheckStatus:
    return CheckStatus.pass_ if ok else CheckStatus.fail
