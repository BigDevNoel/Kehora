"""Build graph (PRD 6, reduced):

    intake -> spec -> request_spec_approval -> spec_gate -(approved)-> create_version
           -> mechanical (object projects, flag PHASE1_OBJECTS) | engine (echo) -> finish

State is `BuildState` (Backend/schemas). Nodes return plain JSON updates so checkpoints hold only
JSON values. Every node emits node_started / node_finished. A node may re-run after a worker
crash (LangGraph resumes from the last completed node), so side effects are idempotent.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import interrupt
from sqlalchemy import func, select

from kehora_agents import prompts
from kehora_agents.mechanical import design_part
from kehora_agents.services import Services, emit, set_status, usage_sink
from kehora_common.clock import utcnow
from kehora_common.flags import Flag, is_enabled
from kehora_db.enums import ApprovalGate, ApprovalStatus, RunStatus
from kehora_db.models import AgentRun, Approval, Artifact, Check, Project, ProjectVersion
from kehora_engines.echo import EchoEngine, EchoInput
from kehora_engines_runner.runner import run_engine
from kehora_llm.types import Message
from kehora_schemas import (
    ArtifactRef,
    ArtifactType,
    BuildState,
    CheckResult,
    CheckStatus,
    IntakeResult,
    PolicyDecision,
    ProjectKind,
    ProjectSpec,
    RunEventType,
)

Node = Callable[[BuildState], Awaitable[dict[str, Any]]]


class PolicyRefusal(Exception):
    """Intake refused the request under the design policy (PRD 11)."""


class VerificationFailed(Exception):
    """A verifier failed; nothing may be shown as done (CLAUDE.md architecture)."""


def _tracked(svc: Services, name: str, fn: Node) -> Any:
    """Wrap a node with node_started / node_finished events."""

    async def wrapper(state: BuildState) -> dict[str, Any]:
        await emit(svc, state.run_id, RunEventType.node_started, node=name)
        update = await fn(state)
        await emit(svc, state.run_id, RunEventType.node_finished, node=name)
        return update

    return wrapper


def build_graph(svc: Services, checkpointer: Any) -> CompiledStateGraph[Any, Any, Any, Any]:
    async def intake(state: BuildState) -> dict[str, Any]:
        result = await svc.gateway.structured(
            "intake",
            IntakeResult,
            [Message.user(state.prompt)],
            system=prompts.load(*prompts.INTAKE),
            on_usage=usage_sink(svc, state.run_id),
        )
        if result.decision == PolicyDecision.refuse:
            raise PolicyRefusal(result.reason)
        return {"kind": result.kind.value}

    async def spec(state: BuildState) -> dict[str, Any]:
        written = await svc.gateway.structured(
            "spec",
            ProjectSpec,
            [Message.user(f"Category from intake: {state.kind}\n\nRequest:\n{state.prompt}")],
            system=prompts.load(*prompts.SPEC),
            on_usage=usage_sink(svc, state.run_id),
        )
        return {"spec": written.model_dump(mode="json")}

    async def request_spec_approval(state: BuildState) -> dict[str, Any]:
        assert state.spec is not None
        async with svc.sessionmaker() as session, session.begin():
            pending = await session.scalar(
                select(Approval).where(
                    Approval.run_id == state.run_id,
                    Approval.gate == ApprovalGate.SPEC,
                    Approval.status == ApprovalStatus.PENDING,
                )
            )
            if pending is None:
                session.add(Approval(run_id=state.run_id, gate=ApprovalGate.SPEC))
        await set_status(svc, state.run_id, RunStatus.AWAITING_APPROVAL)
        await emit(
            svc,
            state.run_id,
            RunEventType.needs_approval,
            {"gate": "spec", "spec": state.spec.model_dump(mode="json")},
            node="request_spec_approval",
        )
        return {}

    async def spec_gate(state: BuildState) -> dict[str, Any]:
        # Pauses the graph; the worker resumes it with the decision stored in `approvals`.
        decision = interrupt({"gate": "spec"})
        return {"spec_approved": bool(decision.get("approved"))}

    async def create_version(state: BuildState) -> dict[str, Any]:
        assert state.spec is not None
        async with svc.sessionmaker() as session, session.begin():
            run = await session.get(AgentRun, state.run_id, with_for_update=True)
            assert run is not None
            if run.version_id is None:  # idempotent on re-run
                last = await session.scalar(
                    select(func.coalesce(func.max(ProjectVersion.number), 0)).where(
                        ProjectVersion.project_id == state.project_id
                    )
                )
                version = ProjectVersion(
                    project_id=state.project_id,
                    number=int(last or 0) + 1,
                    spec=state.spec.model_dump(mode="json"),
                    created_by_run_id=state.run_id,
                )
                session.add(version)
                await session.flush()
                run.version_id = version.id
                project = await session.get(Project, state.project_id)
                assert project is not None
                project.title = state.spec.title
                project.kind = state.spec.kind.value
            version_id = run.version_id
        return {"version_id": str(version_id)}

    async def store(
        state: BuildState,
        node: str,
        name: str,
        data: bytes,
        kind: tuple[ArtifactType, str, str],
        checks: list[CheckResult],
        metadata: dict[str, Any],
    ) -> ArtifactRef:
        """Upload one output, record its artifact and check rows, and emit their events.
        Idempotent on re-run: the S3 key is deterministic and the artifact is looked up first."""
        assert state.version_id is not None
        type_, fmt, content_type = kind
        key = f"projects/{state.project_id}/versions/{state.version_id}/{node}/{name}"
        stored = await asyncio.to_thread(svc.storage.put_bytes, key, data, content_type)
        async with svc.sessionmaker() as session, session.begin():
            artifact = await session.scalar(
                select(Artifact).where(
                    Artifact.version_id == state.version_id, Artifact.s3_key == key
                )
            )
            if artifact is None:
                artifact = Artifact(
                    version_id=state.version_id,
                    type=type_.value,
                    format=fmt,
                    s3_key=key,
                    sha256=stored.sha256,
                    size=stored.size,
                    metadata_=metadata,
                )
                session.add(artifact)
                await session.flush()
            artifact_id = artifact.id
            for check in checks:
                session.add(
                    Check(
                        run_id=state.run_id,
                        artifact_id=artifact_id,
                        engine=check.engine,
                        name=check.name,
                        status=check.status.value,
                        report=check.report,
                    )
                )
        ref = ArtifactRef(
            artifact_id=artifact_id,
            type=type_,
            format=fmt,
            s3_key=key,
            sha256=stored.sha256,
            size=stored.size,
        )
        await emit(
            svc, state.run_id, RunEventType.artifact_created, ref.model_dump(mode="json"), node
        )
        await emit_checks(state, node, checks)
        return ref

    async def emit_checks(state: BuildState, node: str, checks: list[CheckResult]) -> None:
        for check in checks:
            kind = {
                CheckStatus.pass_: RunEventType.check_passed,
                CheckStatus.warn: RunEventType.check_warned,
                CheckStatus.fail: RunEventType.check_failed,
            }[check.status]
            await emit(svc, state.run_id, kind, check.model_dump(mode="json"), node)

    async def engine(state: BuildState) -> dict[str, Any]:
        assert state.spec is not None and state.version_id is not None
        echo = EchoEngine()
        inp = EchoInput(
            message=f"{state.spec.title}\n\n{state.spec.summary}",
            delay_s=svc.settings.echo_delay_s,
        )
        result = await run_engine(svc.sandbox, echo, inp)
        ref = await store(
            state,
            "engine",
            "echo.txt",
            result.output.text.encode(),
            (ArtifactType.log, "txt", "text/plain"),
            result.checks,
            {"engine": echo.name, "duration_ms": result.result.duration_ms},
        )
        if any(c.status == CheckStatus.fail for c in result.checks):
            raise VerificationFailed(f"{echo.name} verifier failed")
        return {
            "artifacts": [ref.model_dump(mode="json")],
            "checks": [c.model_dump(mode="json") for c in result.checks],
        }

    async def mechanical(state: BuildState) -> dict[str, Any]:
        assert state.spec is not None and state.version_id is not None

        async def on_repair(attempt: int, failures: list[str]) -> None:
            await emit(
                svc,
                state.run_id,
                RunEventType.repair_attempt,
                {"attempt": attempt, "failures": failures[:10]},
                "mechanical",
            )

        result = await design_part(
            svc.gateway,
            svc.sandbox,
            state.spec,
            on_usage=usage_sink(svc, state.run_id),
            on_repair=on_repair,
        )
        final = result.final
        meta = {"engine": "cad", "repair_attempts": result.repair_attempts}
        cad_checks = [c for c in final.checks if c.engine == "cad"]
        print_checks = [c for c in final.checks if c.engine != "cad"]
        files = final.cad.files
        refs = [
            await store(
                state,
                "mechanical",
                "script.py",
                final.design.script.encode(),
                (ArtifactType.model, "py", "text/x-python"),
                [] if files else final.checks,  # never built: its checks belong to the script
                meta,
            )
        ]
        for name, kind, checks in (
            ("part.step", (ArtifactType.model, "step", "model/step"), cad_checks),
            ("part.stl", (ArtifactType.mesh, "stl", "model/stl"), print_checks),
            ("part.3mf", (ArtifactType.mesh, "3mf", "model/3mf"), []),
        ):
            if name in files:
                refs.append(await store(state, "mechanical", name, files[name], kind, checks, meta))
        if not result.ok:
            raise VerificationFailed(
                f"mechanical design failed after {result.repair_attempts} repairs: "
                + "; ".join(final.failures)[:500]
            )
        return {
            "artifacts": [r.model_dump(mode="json") for r in refs],
            "checks": [c.model_dump(mode="json") for c in final.checks],
            "repair_attempts": result.repair_attempts,
        }

    async def finish(state: BuildState) -> dict[str, Any]:
        assert state.version_id is not None
        async with svc.sessionmaker() as session, session.begin():
            project = await session.get(Project, state.project_id)
            assert project is not None
            project.current_version_id = uuid.UUID(str(state.version_id))
        await set_status(svc, state.run_id, RunStatus.SUCCEEDED, finished_at=utcnow())
        await emit(
            svc,
            state.run_id,
            RunEventType.run_finished,
            {"version_id": str(state.version_id), "artifacts": len(state.artifacts)},
        )
        return {}

    def after_gate(state: BuildState) -> str:
        return "create_version" if state.spec_approved else END

    def build_step(state: BuildState) -> str:
        assert state.spec is not None
        if is_enabled(Flag.PHASE1_OBJECTS) and state.spec.kind == ProjectKind.object:
            return "mechanical"
        return "engine"

    g = StateGraph(BuildState)
    for name, fn in [
        ("intake", intake),
        ("spec", spec),
        ("create_version", create_version),
        ("engine", engine),
        ("mechanical", mechanical),
    ]:
        g.add_node(name, _tracked(svc, name, fn))
    g.add_node("request_spec_approval", request_spec_approval)
    g.add_node("spec_gate", spec_gate)
    g.add_node("finish", finish)
    g.add_edge(START, "intake")
    g.add_edge("intake", "spec")
    g.add_edge("spec", "request_spec_approval")
    g.add_edge("request_spec_approval", "spec_gate")
    g.add_conditional_edges("spec_gate", after_gate, ["create_version", END])
    g.add_conditional_edges("create_version", build_step, ["mechanical", "engine"])
    g.add_edge("engine", "finish")
    g.add_edge("mechanical", "finish")
    g.add_edge("finish", END)
    return g.compile(checkpointer=checkpointer)
