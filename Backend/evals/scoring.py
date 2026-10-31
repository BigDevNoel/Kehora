"""Score one built object against its case. Pure: no sandbox, no LLM."""

from pydantic import BaseModel, Field

from evals.cases import Category, ObjectCase
from kehora_engines.cad import CadReport
from kehora_schemas import CheckResult, CheckStatus, PrintabilityReport

SUPPORT_FREE_MM2 = 25.0  # matches the printability engine's overhang threshold


class CaseResult(BaseModel):
    id: str
    category: Category
    passed: bool
    failures: list[str] = Field(default_factory=list)
    repair_attempts: int = 0
    cost_usd_micros: int = 0
    model_calls: int = 0
    duration_s: float = 0.0


def score(
    case: ObjectCase,
    cad_report: CadReport | None,
    cad_checks: list[CheckResult],
    printability: PrintabilityReport | None,
    build_error: str | None = None,
) -> list[str]:
    """Return the reasons the case failed; an empty list means it passed."""
    if build_error is not None:
        return [f"build: {build_error}"]
    failures = [
        f"cad.{c.name}: {c.report.get('error') or c.status.value}"
        for c in cad_checks
        if c.status == CheckStatus.fail
    ]
    if cad_report is None or cad_report.brep is None:
        return failures or ["cad: no solid produced"]

    brep, expect = cad_report.brep, case.expect
    if expect.single_body and brep.solid_count != 1:
        failures.append(f"expected one body, got {brep.solid_count}")

    dims = sorted(brep.size_mm, reverse=True)
    for name, rng, value in (
        ("largest", expect.largest_mm, dims[0]),
        ("middle", expect.middle_mm, dims[1]),
        ("smallest", expect.smallest_mm, dims[2]),
    ):
        if rng is not None and not rng.contains(value):
            failures.append(f"{name} side {value:.1f} mm outside [{rng.min}, {rng.max}]")
    if expect.exact_size is not None:
        want = sorted(expect.exact_size.dims_mm, reverse=True)
        # Match stated sizes to the closest sides, largest first.
        got = dims[: len(want)] if len(want) == 3 else _closest(dims, want)
        for w, g in zip(want, got, strict=True):
            if abs(w - g) > expect.exact_size.tolerance_mm:
                failures.append(f"stated size {w} mm came out {g:.2f} mm")

    if printability is None:
        failures.append("printability: no report")
        return failures
    failures += [
        f"print.{i.code.value}: {i.message}"
        for i in printability.issues
        if i.severity.value == "error"
    ]
    # Orientation is a one-click fix at print time, so judge supports on the best orientation.
    # Blocking errors above are judged as delivered: the model must arrive bed-ready.
    overhang = printability.recommended.overhang_area_mm2
    if not expect.supports_allowed and overhang > SUPPORT_FREE_MM2:
        failures.append(
            f"needs supports ({overhang:.0f} mm² overhang), but the prompt asked for none"
        )
    return failures


def _closest(dims: list[float], want: list[float]) -> list[float]:
    remaining = list(dims)
    picked = []
    for w in want:
        best = min(remaining, key=lambda d: abs(d - w))
        remaining.remove(best)
        picked.append(best)
    return picked
