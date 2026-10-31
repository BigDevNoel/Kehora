import ast
from typing import Any

import pytest

from evals.__main__ import main
from evals.builders import ReferenceBuilder
from evals.cases import EVALS_DIR, Category, ExactSize, Expect, ObjectCase, Range, load_cases
from evals.scoring import score
from kehora_engines.cad import BrepReport, CadReport, MeshReport
from kehora_engines.printability.profiles import materials, printers
from kehora_schemas import CheckResult, CheckStatus, PrintabilityReport

CASES = load_cases("objects")


# --- the suite itself ---------------------------------------------------------------------
def test_objects_suite_has_100_unique_cases() -> None:
    assert len(CASES) == 100  # PRD 8.2
    assert len({c.id for c in CASES}) == 100
    assert len({c.prompt for c in CASES}) == 100


def test_every_case_targets_a_shipped_printer_and_material() -> None:
    for case in CASES:
        assert case.printer in printers(), case.id
        assert case.material in materials(), case.id


def test_suite_mixes_categories() -> None:
    counts = {cat: sum(c.category == cat for c in CASES) for cat in Category}
    assert counts[Category.functional] >= 80
    assert counts[Category.organic] >= 5 and counts[Category.hybrid] >= 3


def test_reference_scripts_match_cases_and_assign_result() -> None:
    ids = {c.id for c in CASES}
    scripts = sorted((EVALS_DIR / "objects" / "reference").glob("*.py"))
    assert len(scripts) >= 10
    for path in scripts:
        assert path.stem in ids, f"{path.name} has no case"
        tree = ast.parse(path.read_text(encoding="utf-8"))
        targets = {
            t.id
            for n in ast.walk(tree)
            if isinstance(n, ast.Assign)
            for t in n.targets
            if isinstance(t, ast.Name)
        }
        assert "result" in targets, path.name


def test_case_ids_must_match_file_names(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    suite = tmp_path / "objects"
    suite.mkdir()
    (suite / "a-case.yaml").write_text("id: other-case\nprompt: A prompt long enough.\n")
    monkeypatch.setattr("evals.cases.EVALS_DIR", tmp_path)
    with pytest.raises(ValueError, match="must match"):
        load_cases("objects")


def test_range_rejects_inverted_bounds() -> None:
    with pytest.raises(ValueError, match="min must not exceed max"):
        Range(min=10, max=5)


async def test_reference_builder_skips_cases_without_a_script() -> None:
    builder = ReferenceBuilder()
    built = await builder.build(next(c for c in CASES if c.id == "calibration-cube"))
    assert built is not None and built.script and "result" in built.script
    assert await builder.build(ObjectCase(id="no-such-case", prompt="Nothing to see here.")) is None


def test_suites_without_cases_report_and_pass(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["devices", "mechanisms"]) == 0
    assert "no cases yet" in capsys.readouterr().out


# --- scoring ------------------------------------------------------------------------------
def _cad(size: tuple[float, float, float] = (20, 20, 20), solids: int = 1) -> CadReport:
    return CadReport(
        ok=True,
        brep=BrepReport(
            is_valid=True,
            solid_count=solids,
            volume_mm3=1,
            area_mm2=1,
            bbox_min_mm=(0, 0, 0),
            bbox_max_mm=size,
        ),
        mesh=MeshReport(triangles=12, is_watertight=True, is_winding_consistent=True, volume_mm3=1),
    )


def _print(issues: list[dict[str, Any]] | None = None, overhang: float = 0) -> PrintabilityReport:
    orientation = {
        "rotation_deg": {"x": 0, "y": 0, "z": 0},
        "size_mm": {"x": 20, "y": 20, "z": 20},
        "fits_bed": True,
        "rotate_z_90": False,
        "overhang_area_mm2": overhang,
        "bed_contact_area_mm2": 400,
    }
    issues = issues or []
    return PrintabilityReport.model_validate(
        {
            "printer_id": "prusa-mk4",
            "material_id": "pla",
            "blocking": any(i["severity"] == "error" for i in issues),
            "watertight": True,
            "as_given": orientation,
            "recommended": orientation,
            "min_wall_mm": 5,
            "thin_wall_fraction": 0,
            "issues": issues,
        }
    )


def _case(**expect: Any) -> ObjectCase:
    return ObjectCase(id="c", prompt="A test object prompt.", expect=Expect(**expect))


def test_clean_build_passes() -> None:
    assert score(_case(), _cad(), [], _print()) == []


def test_build_error_and_failed_cad_checks_fail() -> None:
    assert score(_case(), None, [], None, build_error="gave up") == ["build: gave up"]
    failed = CheckResult(
        engine="cad", name="script_runs", status=CheckStatus.fail, report={"error": "boom"}
    )
    no_solid = CadReport(ok=False, stage="script", error="boom")
    assert score(_case(), no_solid, [failed], None) == ["cad.script_runs: boom"]


def test_size_ranges_are_orientation_free() -> None:
    case = _case(largest_mm=Range(min=90, max=110), smallest_mm=Range(max=5))
    assert score(case, _cad((3, 100, 40)), [], _print()) == []
    [failure] = score(case, _cad((3, 120, 40)), [], _print())
    assert "largest side 120.0 mm" in failure


@pytest.mark.parametrize(
    ("dims", "size", "ok"),
    [
        ([100, 70, 70], (70, 70.05, 100), True),
        ([100, 70, 70], (70, 70.3, 100), False),
        ([80], (63, 72, 80.02), True),  # one stated size matches the closest side
        ([60, 60], (60, 40, 60.2), False),
    ],
)
def test_exact_sizes_within_tolerance(
    dims: list[float], size: tuple[float, float, float], ok: bool
) -> None:
    case = _case(exact_size=ExactSize(dims_mm=dims))
    assert (score(case, _cad(size), [], _print()) == []) is ok


def test_bodies_supports_and_blocking_issues() -> None:
    assert score(_case(), _cad(solids=2), [], _print()) == ["expected one body, got 2"]
    assert score(_case(single_body=False), _cad(solids=2), [], _print()) == []

    warning = [{"code": "overhangs", "severity": "warning", "message": "Hangs over air."}]
    assert score(_case(), _cad(), [], _print(warning, overhang=300)) == []
    [failure] = score(_case(supports_allowed=False), _cad(), [], _print(warning, overhang=300))
    assert "needs supports" in failure

    error = [{"code": "exceeds_bed", "severity": "error", "message": "Too big."}]
    assert score(_case(), _cad(), [], _print(error)) == ["print.exceeds_bed: Too big."]
    assert score(_case(), _cad(), [], None) == ["printability: no report"]


# --- real Docker: every reference solution must pass its own case ---------------------------
@pytest.mark.docker
async def test_reference_solutions_pass_in_the_sandbox() -> None:
    from evals.__main__ import run_suite

    results = await run_suite("objects", ReferenceBuilder(), only=set(), jobs=2)
    assert len(results) >= 10
    failed = {r.id: r.failures for r in results if not r.passed}
    assert failed == {}
