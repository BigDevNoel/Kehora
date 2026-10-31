import json
from pathlib import Path

import pytest

from kehora_engines.base import EngineError, SandboxResult
from kehora_engines.cad import (
    IMAGE,
    BrepReport,
    CadEngine,
    CadInput,
    CadOutput,
    CadReport,
    ExpectedSize,
    MeshReport,
)
from kehora_engines_runner.local_docker import LocalDockerSandbox
from kehora_engines_runner.runner import run_engine
from kehora_schemas import CheckStatus

FIXTURES = Path(__file__).parents[1] / "fixtures" / "cad"
EXPORT_BYTES = {"part.step": b"step", "part.stl": b"stl", "part.3mf": b"3mf"}


def _script(name: str) -> str:
    return (FIXTURES / name).read_text()


def _good_report(size: tuple[float, float, float] = (40, 30, 10), solids: int = 1) -> CadReport:
    return CadReport(
        ok=True,
        brep=BrepReport(
            is_valid=True,
            solid_count=solids,
            volume_mm3=12000,
            area_mm2=4400,
            bbox_min_mm=(0, 0, 0),
            bbox_max_mm=size,
        ),
        mesh=MeshReport(
            triangles=12, is_watertight=True, is_winding_consistent=True, volume_mm3=12000
        ),
    )


def _result(
    report: CadReport | None, exit_code: int = 0, outputs: dict[str, bytes] | None = None
) -> SandboxResult:
    files = dict(outputs or {})
    if report is not None:
        files["report.json"] = report.model_dump_json().encode()
    return SandboxResult(exit_code=exit_code, stdout="", stderr="trace", outputs=files)


def _statuses(engine: CadEngine, inp: CadInput, out: CadOutput) -> dict[str, CheckStatus]:
    return {c.name: c.status for c in engine.verify(inp, out)}


# --- pure engine logic (no Docker) ------------------------------------------------------
def test_build_job_ships_harness_script_and_params_without_network() -> None:
    job = CadEngine().build_job(CadInput(script="result = 1", linear_tolerance_mm=0.05))
    assert job.image == IMAGE
    assert job.command == ["python", "/work/in/harness.py"]
    assert set(job.files) == {"harness.py", "script.py", "params.json"}
    assert b"def main()" in job.files["harness.py"]
    assert json.loads(job.files["params.json"])["linear_tolerance_mm"] == 0.05
    assert job.network_allowlist == [] and job.env == {}


def test_parse_returns_report_and_exports() -> None:
    out = CadEngine().parse(CadInput(script="x"), _result(_good_report(), outputs=EXPORT_BYTES))
    assert out.report.ok and out.files == EXPORT_BYTES


def test_parse_turns_timeout_into_a_script_failure() -> None:
    result = SandboxResult(exit_code=137, stdout="", stderr="", outputs={}, timed_out=True)
    out = CadEngine().parse(CadInput(script="x"), result)
    assert out.report.stage == "script" and "timed out" in (out.report.error or "")


@pytest.mark.parametrize(
    ("result", "match"),
    [
        (_result(None, exit_code=1), "exit 1"),
        (_result(None), "exit 0"),
        (
            SandboxResult(exit_code=0, stdout="", stderr="", outputs={"report.json": b"{}"}),
            "invalid",
        ),
        (_result(_good_report(), outputs={"part.stl": b"stl"}), "export is missing"),
    ],
)
def test_parse_rejects_broken_harness_runs(result: SandboxResult, match: str) -> None:
    with pytest.raises(EngineError, match=match):
        CadEngine().parse(CadInput(script="x"), result)


def test_verify_script_failure_is_a_single_failed_check() -> None:
    out = CadOutput(report=CadReport(ok=False, stage="script", error="NameError: boxx"))
    [check] = CadEngine().verify(CadInput(script="x"), out)
    assert (check.name, check.status) == ("script_runs", CheckStatus.fail)
    assert check.report["error"] == "NameError: boxx"


def test_verify_good_part_passes_every_check() -> None:
    inp = CadInput(script="x", expected_size_mm=ExpectedSize(x=40, y=30, z=10))
    assert _statuses(CadEngine(), inp, CadOutput(report=_good_report())) == {
        "script_runs": CheckStatus.pass_,
        "solid_valid": CheckStatus.pass_,
        "watertight": CheckStatus.pass_,
        "dimensions": CheckStatus.pass_,
    }


def test_verify_fails_invalid_and_leaky_solids() -> None:
    report = _good_report()
    assert report.brep is not None and report.mesh is not None
    report.brep.is_valid = False
    report.mesh.is_watertight = False
    statuses = _statuses(CadEngine(), CadInput(script="x"), CadOutput(report=report))
    assert statuses["solid_valid"] == CheckStatus.fail
    assert statuses["watertight"] == CheckStatus.fail
    assert "dimensions" not in statuses


def test_verify_warns_on_multiple_bodies() -> None:
    out = CadOutput(report=_good_report(solids=2))
    assert _statuses(CadEngine(), CadInput(script="x"), out)["single_body"] == CheckStatus.warn


@pytest.mark.parametrize(
    ("size", "expected", "status"),
    [
        ((40.09, 30, 10), ExpectedSize(x=40), CheckStatus.pass_),
        ((40.11, 30, 10), ExpectedSize(x=40), CheckStatus.fail),
        ((40, 30, 99), ExpectedSize(x=40, y=30), CheckStatus.pass_),
        ((40, 29.5, 10), ExpectedSize(y=30), CheckStatus.fail),
    ],
)
def test_verify_dimensions_within_tolerance(
    size: tuple[float, float, float], expected: ExpectedSize, status: CheckStatus
) -> None:
    inp = CadInput(script="x", expected_size_mm=expected)
    [check] = [
        c
        for c in CadEngine().verify(inp, CadOutput(report=_good_report(size)))
        if c.name == "dimensions"
    ]
    assert check.status == status
    assert set(check.report["axes"]) == {k for k, v in expected.model_dump().items() if v}


# --- real Docker (CAD sandbox image, `make engine-images`) ------------------------------
@pytest.fixture(scope="module")
def sandbox() -> LocalDockerSandbox:
    return LocalDockerSandbox(egress_proxy="http://egress:8888", egress_allowlist=set())


async def _run(
    sandbox: LocalDockerSandbox, inp: CadInput
) -> tuple[CadOutput, dict[str, CheckStatus]]:
    engine = CadEngine()
    run = await run_engine(sandbox, engine, inp)
    return run.output, {c.name: c.status for c in run.checks}


@pytest.mark.docker
async def test_box_exports_and_passes(sandbox: LocalDockerSandbox) -> None:
    inp = CadInput(script=_script("box.py"), expected_size_mm=ExpectedSize(x=40, y=30, z=10))
    out, statuses = await _run(sandbox, inp)
    assert set(statuses.values()) == {CheckStatus.pass_}, out.report
    assert out.files["part.step"].startswith(b"ISO-10303-21")
    assert out.files["part.3mf"].startswith(b"PK")  # 3MF is a zip package
    assert out.report.brep is not None and out.report.brep.volume_mm3 == pytest.approx(12000)
    assert out.report.mesh is not None and out.report.mesh.volume_mm3 == pytest.approx(
        12000, rel=1e-3
    )


@pytest.mark.docker
async def test_phone_stand_is_a_watertight_single_body(sandbox: LocalDockerSandbox) -> None:
    out, statuses = await _run(sandbox, CadInput(script=_script("phone_stand.py")))
    assert statuses == {
        "script_runs": CheckStatus.pass_,
        "solid_valid": CheckStatus.pass_,
        "watertight": CheckStatus.pass_,
    }, out.report


@pytest.mark.docker
@pytest.mark.parametrize(
    ("fixture", "stage", "needle"),
    [
        ("syntax_error.py", "script", "SyntaxError"),
        ("raises.py", "script", "wall thickness must be positive"),
        ("no_result.py", "result", "`result`"),
    ],
)
async def test_script_errors_come_back_as_repairable_reports(
    sandbox: LocalDockerSandbox, fixture: str, stage: str, needle: str
) -> None:
    out, statuses = await _run(sandbox, CadInput(script=_script(fixture)))
    assert statuses == {"script_runs": CheckStatus.fail}
    assert out.report.stage == stage and needle in (out.report.error or "")
    assert "harness.py" not in (out.report.error or ""), "traceback should show only the script"


@pytest.mark.docker
async def test_open_face_is_reported_as_no_solid(sandbox: LocalDockerSandbox) -> None:
    out, statuses = await _run(sandbox, CadInput(script=_script("open_face.py")))
    assert statuses == {"script_runs": CheckStatus.fail}
    assert out.report.stage == "result"
    assert "contains no solid (1 faces" in (out.report.error or "")


@pytest.mark.docker
async def test_script_has_no_network(sandbox: LocalDockerSandbox) -> None:
    script = "import socket\nsocket.create_connection(('1.1.1.1', 80), timeout=3)\nresult = 1\n"
    out, _ = await _run(sandbox, CadInput(script=script))
    assert out.report.stage == "script"
    assert "Network is unreachable" in (out.report.error or "")


def test_make_builds_the_image_tag_the_engine_runs() -> None:
    makefile = (Path(__file__).parents[3] / "Makefile").read_text()
    assert f"-t {IMAGE} Backend/infra/docker/engines/cad" in makefile
