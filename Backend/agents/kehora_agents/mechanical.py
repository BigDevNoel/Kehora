"""Mechanical agent: spec -> build123d script -> CAD + printability verifiers -> repair loop.

PRD 6 (specialist subgraph, max 5 repair loops), ADR-0012. Independent of the database and the
event stream so the eval runner can drive it directly; the graph node passes `on_repair` to emit
`repair_attempt` events. Scripts run only in the sandbox (CLAUDE.md rule 4).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from kehora_agents import prompts
from kehora_engines.base import EngineError
from kehora_engines.cad import CadEngine, CadInput, CadOutput, CadReport, ExpectedSize
from kehora_engines.printability import PrintabilityEngine, PrintabilityInput
from kehora_engines.printability.profiles import materials, printers
from kehora_engines_runner.runner import run_engine
from kehora_engines_runner.sandbox import SandboxProvider
from kehora_llm.gateway import Gateway, UsageSink
from kehora_llm.types import Message
from kehora_schemas import (
    CheckResult,
    CheckStatus,
    Material,
    MechanicalDesign,
    PrintabilityReport,
    PrinterProfile,
    ProjectSpec,
)

MAX_REPAIRS = 5  # PRD 6; BuildState.repair_attempts caps at 5 too
DEFAULT_PRINTER = "prusa-mk4"
DEFAULT_MATERIAL = "pla"

RepairSink = Callable[[int, list[str]], Awaitable[None]]


async def _no_repair_sink(attempt: int, failures: list[str]) -> None:
    return None


@dataclass
class Verification:
    design: MechanicalDesign
    cad: CadOutput
    checks: list[CheckResult]
    printability: PrintabilityReport | None
    failures: list[str]

    @property
    def ok(self) -> bool:
        return not self.failures


@dataclass
class DesignResult:
    final: Verification
    repair_attempts: int
    history: list[Verification] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.final.ok


def pick_printer(spec: ProjectSpec) -> PrinterProfile:
    return _pick(
        printers(), spec.constraints.printer if spec.constraints else None, DEFAULT_PRINTER
    )


def pick_material(spec: ProjectSpec) -> Material:
    wanted = spec.constraints.material if spec.constraints else None
    return _pick(materials(), wanted, DEFAULT_MATERIAL)


def _pick[T: (PrinterProfile, Material)](
    options: dict[str, T], wanted: str | None, default: str
) -> T:
    """Match free text from the spec ("Bambu A1 mini", "petg") to a shipped profile."""
    if wanted:
        text = wanted.strip().lower()
        if text in options:
            return options[text]
        for item in options.values():
            if item.name.lower() in text or text in item.name.lower():
                return item
    return options[default]


def brief(spec: ProjectSpec, printer: PrinterProfile, material: Material) -> str:
    vol = printer.build_volume_mm
    return "\n".join(
        [
            f"Printer: {printer.name}, build volume {vol.x:g} x {vol.y:g} x {vol.z:g} mm, "
            f"nozzle {printer.nozzle_mm:g} mm.",
            f"Material: {material.name}, max_overhang_deg {material.max_overhang_deg:g}, "
            f"min_wall_mm {material.min_wall_lines * printer.nozzle_mm:g}.",
            "",
            "Approved spec (JSON):",
            spec.model_dump_json(indent=2, exclude_none=True),
        ]
    )


async def verify(
    sandbox: SandboxProvider,
    design: MechanicalDesign,
    printer: PrinterProfile,
    material: Material,
) -> Verification:
    size = design.intended_size_mm
    try:
        cad_run = await run_engine(
            sandbox,
            CadEngine(),
            CadInput(
                script=design.script, expected_size_mm=ExpectedSize(x=size.x, y=size.y, z=size.z)
            ),
        )
    except EngineError as e:  # e.g. the script ran out of memory: the agent must fix it
        crashed = CadOutput(report=CadReport(ok=False, stage="script", error=str(e)))
        return Verification(design, crashed, [], None, [f"script_runs: {e}"])
    checks = list(cad_run.checks)
    failures = [_describe(c) for c in checks if c.status == CheckStatus.fail]
    report = None
    if not failures:
        inp = PrintabilityInput(
            stl=cad_run.output.files["part.stl"], printer=printer, material=material
        )
        print_run = await run_engine(sandbox, PrintabilityEngine(), inp)
        checks += print_run.checks
        report = print_run.output.report
        if report is None:
            failures.append(f"printability: {print_run.output.load_error}")
        else:
            failures += [
                f"printability {i.code.value}: {i.message}"
                for i in report.issues
                if i.severity.value == "error"
            ]
    return Verification(design, cad_run.output, checks, report, failures)


async def design_part(
    gateway: Gateway,
    sandbox: SandboxProvider,
    spec: ProjectSpec,
    *,
    on_usage: UsageSink | None = None,
    on_repair: RepairSink = _no_repair_sink,
) -> DesignResult:
    printer, material = pick_printer(spec), pick_material(spec)
    text = brief(spec, printer, material)
    usage: dict[str, Any] = {"on_usage": on_usage} if on_usage else {}

    design = await gateway.structured(
        "mechanical",
        MechanicalDesign,
        [Message.user(text)],
        system=prompts.load(*prompts.MECHANICAL),
        **usage,
    )
    history = [await verify(sandbox, design, printer, material)]
    while not history[-1].ok and len(history) <= MAX_REPAIRS:
        attempt = len(history)
        await on_repair(attempt, history[-1].failures)
        design = await gateway.structured(
            "repair",
            MechanicalDesign,
            [Message.user(_repair_message(text, history[-1]))],
            system=prompts.load(*prompts.MECHANICAL_REPAIR),
            **usage,
        )
        history.append(await verify(sandbox, design, printer, material))
    return DesignResult(final=history[-1], repair_attempts=len(history) - 1, history=history)


def _describe(check: CheckResult) -> str:
    report = check.report
    if check.name == "script_runs":
        return f"script_runs ({report.get('stage')}): {report.get('error')}"
    if check.name == "dimensions":
        axes = report.get("axes", {})
        bad = ", ".join(
            f"{axis} intended {a['expected_mm']} got {a['actual_mm']}"
            for axis, a in axes.items()
            if not a["ok"]
        )
        return f"dimensions: {bad}"
    return f"{check.name}: {report}"


def _repair_message(text: str, last: Verification) -> str:
    size = last.design.intended_size_mm
    return "\n".join(
        [
            "Brief:",
            text,
            "",
            f"Previous intended_size_mm: x={size.x:g} y={size.y:g} z={size.z:g}",
            "Previous script:",
            "```python",
            last.design.script,
            "```",
            "",
            "Verifier failures:",
            *(f"- {f}" for f in last.failures),
        ]
    )
