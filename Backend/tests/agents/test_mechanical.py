"""Mechanical agent loop with a scripted fake LLM and a fake sandbox (no Docker, no DB)."""

import json
from typing import Any

import pytest

from kehora_agents import prompts
from kehora_agents.mechanical import MAX_REPAIRS, design_part, pick_material, pick_printer
from kehora_engines.base import SandboxJob, SandboxResult
from kehora_llm.adapters.fake import FakeAdapter
from kehora_llm.gateway import Gateway
from kehora_llm.routing import RoutingTable
from kehora_llm.types import Completion
from kehora_schemas import Constraints, ProjectKind, ProjectSpec

SPEC = ProjectSpec(
    schema_version=0, kind=ProjectKind.object, title="Cube", summary="A 20 mm calibration cube."
)
ORIENTATION = {
    "rotation_deg": {"x": 0, "y": 0, "z": 0},
    "size_mm": {"x": 20, "y": 20, "z": 20},
    "fits_bed": True,
    "rotate_z_90": False,
    "overhang_area_mm2": 0,
    "bed_contact_area_mm2": 400,
}


class FakeCadSandbox:
    """Answers CAD jobs by markers in the script and printability jobs by markers in the STL."""

    name = "fake"

    def __init__(self) -> None:
        self.jobs: list[SandboxJob] = []

    async def run(self, job: SandboxJob) -> SandboxResult:
        self.jobs.append(job)
        if "script.py" in job.files:
            return self._cad(job.files["script.py"].decode())
        return self._printability(job.files["part.stl"].decode().strip())

    def _cad(self, script: str) -> SandboxResult:
        if "CRASH" in script:
            return SandboxResult(exit_code=137, stdout="", stderr="Killed", outputs={})
        if "BROKEN" in script:
            report: dict[str, Any] = {"ok": False, "stage": "script", "error": "NameError: Boxx"}
            return _result(report)
        size = 30 if "WRONGSIZE" in script else 20
        report = {
            "ok": True,
            "brep": {
                "is_valid": True,
                "solid_count": 1,
                "volume_mm3": 8000,
                "area_mm2": 2400,
                "bbox_min_mm": [0, 0, 0],
                "bbox_max_mm": [size, 20, 20],
            },
            "mesh": {
                "triangles": 12,
                "is_watertight": True,
                "is_winding_consistent": True,
                "volume_mm3": 8000,
            },
        }
        marker = "TOOBIG" if "TOOBIG" in script else "fine"
        files = {"part.step": b"step", "part.stl": marker.encode().ljust(84), "part.3mf": b"3mf"}
        return _result(report, files)

    def _printability(self, marker: str) -> SandboxResult:
        issues = []
        if marker == "TOOBIG":
            issues = [
                {"code": "exceeds_bed", "severity": "error", "message": "Too big.", "fixes": []}
            ]
        report = {
            "printer_id": "prusa-mk4",
            "material_id": "pla",
            "blocking": bool(issues),
            "watertight": True,
            "as_given": ORIENTATION,
            "recommended": ORIENTATION,
            "min_wall_mm": 20,
            "thin_wall_fraction": 0,
            "issues": issues,
        }
        return _result(report)


def _result(report: dict[str, Any], files: dict[str, bytes] | None = None) -> SandboxResult:
    outputs = {"report.json": json.dumps(report).encode(), **(files or {})}
    return SandboxResult(exit_code=0, stdout="", stderr="", outputs=outputs)


def _design(script: str, x: float = 20) -> Completion:
    body = {"script": script, "intended_size_mm": {"x": x, "y": 20, "z": 20}, "notes": "n"}
    return Completion(provider="fake", model="fake-large", text=json.dumps(body))


def _gateway(*designs: Completion) -> tuple[Gateway, FakeAdapter]:
    fake = FakeAdapter()
    fake.scripted.extend(designs)
    return Gateway(RoutingTable.load("test"), {"fake": fake}), fake


async def test_first_design_that_passes_needs_no_repair() -> None:
    gateway, fake = _gateway(_design("result = Box(20, 20, 20)"))
    sandbox = FakeCadSandbox()
    result = await design_part(gateway, sandbox, SPEC)
    assert result.ok and result.repair_attempts == 0
    assert [c.name for c in result.final.checks] == [
        "script_runs",
        "solid_valid",
        "watertight",
        "dimensions",
        "printable",
    ]
    assert len(fake.calls) == 1 and len(sandbox.jobs) == 2
    request = fake.calls[0][1]
    assert request.system == prompts.load(*prompts.MECHANICAL)
    assert "Prusa MK4" in request.messages[0].content[-1].text  # type: ignore[union-attr]


async def test_script_error_is_repaired_with_the_traceback() -> None:
    gateway, fake = _gateway(_design("BROKEN"), _design("result = Box(20, 20, 20)"))
    seen: list[tuple[int, list[str]]] = []

    async def on_repair(attempt: int, failures: list[str]) -> None:
        seen.append((attempt, failures))

    result = await design_part(gateway, FakeCadSandbox(), SPEC, on_repair=on_repair)
    assert result.ok and result.repair_attempts == 1
    assert seen == [(1, ["script_runs (script): NameError: Boxx"])]
    repair = fake.calls[1][1]
    assert repair.system == prompts.load(*prompts.MECHANICAL_REPAIR)
    text = repair.messages[0].content[-1].text  # type: ignore[union-attr]
    assert "BROKEN" in text and "NameError: Boxx" in text


@pytest.mark.parametrize(
    ("script", "x", "needle"),
    [
        ("WRONGSIZE", 20, "dimensions: x intended 20.0 got 30"),
        ("TOOBIG", 20, "printability exceeds_bed: Too big."),
        ("CRASH", 20, "script_runs: cad harness failed (exit 137)"),
    ],
)
async def test_verifier_failures_trigger_a_repair(script: str, x: float, needle: str) -> None:
    gateway, _ = _gateway(_design(script, x), _design("result = Box(20, 20, 20)"))
    seen: list[str] = []

    async def on_repair(attempt: int, failures: list[str]) -> None:
        seen.extend(failures)

    result = await design_part(gateway, FakeCadSandbox(), SPEC, on_repair=on_repair)
    assert result.ok and result.repair_attempts == 1
    assert any(needle in f for f in seen), seen


async def test_gives_up_after_five_repairs() -> None:
    gateway, fake = _gateway(*[_design("BROKEN")] * (MAX_REPAIRS + 1))
    result = await design_part(gateway, FakeCadSandbox(), SPEC)
    assert not result.ok and result.repair_attempts == MAX_REPAIRS
    assert len(result.history) == MAX_REPAIRS + 1 == len(fake.calls)


@pytest.mark.parametrize(
    ("printer", "material", "want_printer", "want_material"),
    [
        (None, None, "prusa-mk4", "pla"),
        ("Bambu Lab A1 mini", "PETG", "bambu-a1-mini", "petg"),
        ("bambu-x1c", "tpu", "bambu-x1c", "tpu"),
        ("some unknown printer", "wood", "prusa-mk4", "pla"),
    ],
)
def test_printer_and_material_come_from_the_spec(
    printer: str | None, material: str | None, want_printer: str, want_material: str
) -> None:
    spec = SPEC.model_copy(update={"constraints": Constraints(printer=printer, material=material)})
    assert pick_printer(spec).id == want_printer
    assert pick_material(spec).id == want_material
