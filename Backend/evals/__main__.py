"""`make evals`: run the eval suites and print pass rates (CLAUDE.md rule 9).

    uv run python -m evals                      # every suite, reference builder
    uv run python -m evals objects --only phone-stand-basic --jobs 4 --gate 0.9

Each case's final script is re-verified here through the CAD and printability engines in the
sandbox, independent of whatever the builder claims. Results go to evals/results/ (git-ignored).
"""

import argparse
import asyncio
import json
import sys
import time
from collections import defaultdict

from evals.builders import BUILDERS, Builder
from evals.cases import EVALS_DIR, ObjectCase, load_cases
from evals.scoring import CaseResult, score
from kehora_common.settings import Settings
from kehora_engines.base import EngineError
from kehora_engines.cad import CadEngine, CadInput
from kehora_engines.printability import PrintabilityEngine, PrintabilityInput
from kehora_engines.printability.profiles import materials, printers
from kehora_engines_runner.runner import build_sandbox, run_engine
from kehora_engines_runner.sandbox import SandboxProvider

SUITES = ("objects", "devices", "enclosures", "mechanisms")
RUNNABLE = {"objects"}


async def run_case(
    sandbox: SandboxProvider, builder: Builder, case: ObjectCase
) -> CaseResult | None:
    start = time.monotonic()
    built = await builder.build(case)
    if built is None:
        return None
    result = CaseResult(
        id=case.id, category=case.category, passed=False, repair_attempts=built.repair_attempts
    )
    try:
        if built.script is None:
            result.failures = score(case, None, [], None, build_error=built.error or "no script")
            return result
        cad = await run_engine(sandbox, CadEngine(), CadInput(script=built.script))
        report = None
        if cad.output.report.ok and "part.stl" in cad.output.files:
            inp = PrintabilityInput(
                stl=cad.output.files["part.stl"],
                printer=printers()[case.printer],
                material=materials()[case.material],
            )
            report = (await run_engine(sandbox, PrintabilityEngine(), inp)).output.report
        result.failures = score(case, cad.output.report, cad.checks, report)
    except EngineError as e:
        result.failures = [f"engine: {e}"]
    finally:
        result.duration_s = round(time.monotonic() - start, 1)
    result.passed = not result.failures
    return result


async def run_suite(suite: str, builder: Builder, only: set[str], jobs: int) -> list[CaseResult]:
    cases = [c for c in load_cases(suite) if not only or c.id in only]
    sandbox = build_sandbox(Settings())
    gate = asyncio.Semaphore(jobs)

    async def one(case: ObjectCase) -> CaseResult | None:
        async with gate:
            return await run_case(sandbox, builder, case)

    results = await asyncio.gather(*(one(c) for c in cases))
    return [r for r in results if r is not None]


def report(suite: str, total: int, results: list[CaseResult]) -> float:
    by_cat: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        by_cat[r.category.value].append(r.passed)
        if not r.passed:
            print(f"  FAIL {r.id}: {'; '.join(r.failures)[:300]}")
    passed = sum(r.passed for r in results)
    rate = passed / total if total else 0.0
    built_rate = passed / len(results) if results else 0.0
    print(
        f"{suite:<12} {passed}/{total} passed ({rate:.0%}); "
        f"{len(results)} built, {built_rate:.0%} of those passed"
    )
    for cat, flags in sorted(by_cat.items()):
        print(f"  {cat:<11} {sum(flags)}/{len(flags)}")
    return rate


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals")
    parser.add_argument("suites", nargs="*", default=list(SUITES))
    parser.add_argument("--builder", choices=sorted(BUILDERS), default="reference")
    parser.add_argument("--only", action="append", default=[], help="case id (repeatable)")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--gate", type=float, default=None, help="fail below this pass rate")
    args = parser.parse_args(argv)

    ok = True
    for suite in args.suites:
        total = (
            len([c for c in load_cases(suite) if not args.only or c.id in args.only])
            if suite in RUNNABLE
            else 0
        )
        if suite not in RUNNABLE or total == 0:
            print(f"{suite:<12} no cases yet")
            continue
        builder = BUILDERS[args.builder](suite)
        results = asyncio.run(run_suite(suite, builder, set(args.only), args.jobs))
        rate = report(suite, total, results)
        out = EVALS_DIR / "results"
        out.mkdir(exist_ok=True)
        (out / f"{suite}-{args.builder}.json").write_text(
            json.dumps([r.model_dump(mode="json") for r in results], indent=2)
        )
        if args.gate is not None and rate < args.gate:
            print(
                f"{suite}: pass rate {rate:.0%} is below the gate {args.gate:.0%}", file=sys.stderr
            )
            ok = False
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
