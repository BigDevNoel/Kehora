from typing import Any

import numpy as np
import pytest
import trimesh

from kehora_engines.base import EngineError, SandboxResult
from kehora_engines.printability import (
    PrintabilityEngine,
    PrintabilityInput,
    PrintabilityOutput,
)
from kehora_engines.printability.analysis import analyze
from kehora_engines.printability.profiles import DATA_DIR, materials, printers
from kehora_engines_runner.local_docker import LocalDockerSandbox
from kehora_engines_runner.runner import run_engine
from kehora_schemas import CheckStatus, PrintabilityReport

MK4 = printers()["prusa-mk4"]  # 250 x 210 x 220, 0.4 mm nozzle
PLA = materials()["pla"]  # 50 degree overhangs, 2 wall lines -> 0.8 mm min wall


def _box(
    x: float, y: float, z: float, at: tuple[float, float, float] = (0, 0, 0)
) -> trimesh.Trimesh:
    mesh: trimesh.Trimesh = trimesh.creation.box(extents=(x, y, z))
    mesh.apply_translation(np.array(at) + np.array([x, y, z]) / 2)
    return mesh


def _analyze(mesh: trimesh.Trimesh) -> dict[str, Any]:
    report = analyze(mesh, MK4.model_dump(mode="json"), PLA.model_dump(mode="json"), 400, 0)
    PrintabilityReport.model_validate(report)  # the harness output must match the schema
    return report


def _codes(report: dict[str, Any]) -> dict[str, str]:
    return {i["code"]: i["severity"] for i in report["issues"]}


def _stl(mesh: trimesh.Trimesh) -> bytes:
    data = mesh.export(file_type="stl")
    assert isinstance(data, bytes)
    return data


# --- shipped profiles --------------------------------------------------------------------
def test_shipped_profiles_validate_and_match_file_names() -> None:
    assert {"prusa-mk4", "bambu-x1c", "creality-ender-3-v3"} <= set(printers())
    assert set(materials()) == {"pla", "petg", "abs", "tpu"}
    for folder, items in (("printer-profiles", printers()), ("materials", materials())):
        assert {p.stem for p in (DATA_DIR / folder).glob("*.yaml")} == set(items)


# --- analysis (numpy + trimesh on the host) -----------------------------------------------
def test_cube_prints_cleanly() -> None:
    report = _analyze(_box(20, 20, 20))
    assert report["issues"] == [] and not report["blocking"]
    assert report["as_given"]["fits_bed"] and report["as_given"]["overhang_area_mm2"] == 0
    assert report["as_given"]["bed_contact_area_mm2"] == pytest.approx(400)
    assert report["min_wall_mm"] == pytest.approx(20, abs=0.01)
    assert report["recommended"]["rotation_deg"] == {"x": 0, "y": 0, "z": 0}


def test_tall_part_fits_only_when_laid_down() -> None:
    report = _analyze(_box(10, 10, 240))
    assert not report["as_given"]["fits_bed"] and report["recommended"]["fits_bed"]
    assert report["recommended"]["size_mm"]["z"] == pytest.approx(10)
    [issue] = report["issues"]
    assert (issue["code"], issue["severity"]) == ("exceeds_bed", "error")
    assert issue["fixes"] == ["reorient", "split_for_bed"] and report["blocking"]


def test_part_bigger_than_any_orientation_needs_splitting() -> None:
    [issue] = _analyze(_box(300, 300, 10))["issues"]
    assert issue["code"] == "exceeds_bed" and issue["fixes"] == ["split_for_bed"]


def test_plate_fits_after_turning_on_the_bed() -> None:
    report = _analyze(_box(200, 240, 10))
    assert report["as_given"]["fits_bed"] and report["as_given"]["rotate_z_90"]
    assert "exceeds_bed" not in _codes(report)


@pytest.mark.parametrize(
    ("thickness", "code", "severity"),
    [(0.3, "walls_too_thin", "error"), (0.6, "thin_walls", "warning"), (1.2, None, None)],
)
def test_wall_thickness_against_nozzle_and_wall_lines(
    thickness: float, code: str | None, severity: str | None
) -> None:
    report = _analyze(_box(20, 20, thickness))
    assert report["min_wall_mm"] == pytest.approx(thickness, abs=0.01)
    wall_codes = {k: v for k, v in _codes(report).items() if "wall" in k}
    assert wall_codes == ({code: severity} if code else {})


def test_overhang_suggests_flipping_the_mushroom() -> None:
    mushroom = trimesh.util.concatenate(
        [_box(10, 10, 20, (15, 15, 0)), _box(40, 40, 5, (0, 0, 20))]
    )
    assert isinstance(mushroom, trimesh.Trimesh)
    report = _analyze(mushroom)
    assert report["as_given"]["overhang_area_mm2"] == pytest.approx(1600)
    assert report["recommended"]["rotation_deg"]["x"] == 180
    assert report["recommended"]["overhang_area_mm2"] == pytest.approx(100)
    [issue] = [i for i in report["issues"] if i["code"] == "overhangs"]
    assert issue["severity"] == "warning" and issue["fixes"] == ["reorient", "add_supports"]
    assert not report["blocking"]


def test_sphere_warns_about_bed_contact_and_overhang() -> None:
    codes = _codes(_analyze(trimesh.creation.icosphere(subdivisions=3, radius=10)))
    assert codes == {"small_bed_contact": "warning", "overhangs": "warning"}


def test_open_mesh_is_blocking_and_skips_wall_rays() -> None:
    mesh = _box(20, 20, 20)
    mesh.update_faces(np.arange(len(mesh.faces)) != 0)
    report = _analyze(mesh)
    assert not report["watertight"] and report["blocking"]
    assert report["min_wall_mm"] is None
    assert _codes(report)["not_watertight"] == "error"


def test_analysis_is_deterministic_for_a_seed() -> None:
    mesh = trimesh.creation.icosphere(subdivisions=2, radius=8)
    assert _analyze(mesh) == _analyze(mesh)


# --- engine wrapper -----------------------------------------------------------------------
def _input(mesh: trimesh.Trimesh | None = None) -> PrintabilityInput:
    return PrintabilityInput(stl=_stl(mesh or _box(20, 20, 20)), printer=MK4, material=PLA)


def _report(**overrides: Any) -> PrintabilityReport:
    report = _analyze(_box(20, 20, 20))
    return PrintabilityReport.model_validate({**report, **overrides})


def test_build_job_ships_analysis_mesh_and_profiles_without_network() -> None:
    inp = _input()
    job = PrintabilityEngine().build_job(inp)
    assert set(job.files) == {"harness.py", "analysis.py", "part.stl", "params.json"}
    assert job.files["part.stl"] == inp.stl and job.network_allowlist == []
    assert b'"prusa-mk4"' in job.files["params.json"]


def test_parse_reads_report_and_load_errors() -> None:
    engine, inp = PrintabilityEngine(), _input()
    ok = SandboxResult(
        exit_code=0,
        stdout="",
        stderr="",
        outputs={"report.json": _report().model_dump_json().encode()},
    )
    assert engine.parse(inp, ok).report is not None
    bad_mesh = SandboxResult(
        exit_code=3, stdout="", stderr="", outputs={"load_error.txt": b"ValueError: not an STL"}
    )
    out = engine.parse(inp, bad_mesh)
    assert out.report is None and out.load_error == "ValueError: not an STL"
    [check] = engine.verify(inp, out)
    assert (check.name, check.status) == ("mesh_loads", CheckStatus.fail)


@pytest.mark.parametrize(
    "result",
    [
        SandboxResult(exit_code=1, stdout="", stderr="boom", outputs={}),
        SandboxResult(exit_code=0, stdout="", stderr="", outputs={"report.json": b"{}"}),
    ],
)
def test_parse_rejects_broken_harness_runs(result: SandboxResult) -> None:
    with pytest.raises(EngineError):
        PrintabilityEngine().parse(_input(), result)


@pytest.mark.parametrize(
    ("overrides", "status"),
    [
        ({}, CheckStatus.pass_),
        (
            {"issues": [{"code": "overhangs", "severity": "warning", "message": "m"}]},
            CheckStatus.warn,
        ),
        (
            {
                "blocking": True,
                "issues": [{"code": "exceeds_bed", "severity": "error", "message": "m"}],
            },
            CheckStatus.fail,
        ),
    ],
)
def test_verify_maps_report_to_a_single_check(
    overrides: dict[str, Any], status: CheckStatus
) -> None:
    [check] = PrintabilityEngine().verify(_input(), PrintabilityOutput(report=_report(**overrides)))
    assert (check.name, check.status) == ("printable", status)
    assert check.report["printer_id"] == "prusa-mk4"


# --- real Docker (runs in the CAD sandbox image) ------------------------------------------
@pytest.fixture(scope="module")
def sandbox() -> LocalDockerSandbox:
    return LocalDockerSandbox(egress_proxy="http://egress:8888", egress_allowlist=set())


@pytest.mark.docker
async def test_sandbox_report_matches_host_analysis(sandbox: LocalDockerSandbox) -> None:
    mesh = _box(10, 10, 240)
    inp = PrintabilityInput(stl=_stl(mesh), printer=MK4, material=PLA, samples=400)
    run = await run_engine(sandbox, PrintabilityEngine(), inp)
    assert run.output.report is not None
    assert run.output.report.model_dump(mode="json") == _analyze(
        trimesh.load_mesh(trimesh.util.wrap_as_stream(_stl(mesh)), file_type="stl")
    )
    assert run.checks[0].status == CheckStatus.fail


@pytest.mark.docker
async def test_sandbox_reports_unreadable_mesh(sandbox: LocalDockerSandbox) -> None:
    inp = PrintabilityInput(stl=b"solid nonsense\n" * 10, printer=MK4, material=PLA)
    run = await run_engine(sandbox, PrintabilityEngine(), inp)
    assert run.checks[0].name == "mesh_loads" and run.checks[0].status == CheckStatus.fail
