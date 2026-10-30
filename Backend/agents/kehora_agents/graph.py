"""Phase 0 build graph (PRD 6, reduced):

    intake -> spec -> request_spec_approval -> spec_gate -(approved)-> create_version
           -> engine (echo, in the sandbox) -> finish

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
from kehora_agents.services import Services, emit, set_status, usage_sink
from kehora_common.clock import utcnow
from kehora_db.enums import ApprovalGate, ApprovalStatus, RunStatus
from kehora_db.models import AgentRun, Approval, Artifact, Check, Project, ProjectVersion
from kehora_engines.echo import EchoEngine, EchoInput
from kehora_engines_runner.runner import run_engine
from kehora_llm.types import Message
from kehora_schemas import (
    ArtifactRef,
    ArtifactType,
    BuildState,
    CheckStatus,
    IntakeResult,
    PolicyDecision,
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

    async def engine(state: BuildState) -> dict[str, Any]:
        assert state.spec is not None and state.version_id is not None
        echo = EchoEngine()
        inp = EchoInput(
            message=f"{state.spec.title}\n\n{state.spec.summary}",
            delay_s=svc.settings.echo_delay_s,
        )
        result = await run_engine(svc.sandbox, echo, inp)
        key = f"projects/{state.project_id}/versions/{state.version_id}/echo/echo.txt"
        stored = await asyncio.to_thread(
            svc.storage.put_bytes, key, result.output.text.encode(), "text/plain"
        )
        async with svc.sessionmaker() as session, session.begin():
            artifact = await session.scalar(
                select(Artifact).where(
                    Artifact.version_id == state.version_id, Artifact.s3_key == key
                )
            )
            if artifact is None:
                artifact = Artifact(
                    version_id=state.version_id,
                    type=ArtifactType.log.value,
                    format="txt",
                    s3_key=key,
                    sha256=stored.sha256,
                    size=stored.size,
                    metadata_={"engine": echo.name, "duration_ms": result.result.duration_ms},
                )
                session.add(artifact)
                await session.flush()
            artifact_id = artifact.id
            for check in result.checks:
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
            type=ArtifactType.log,
            format="txt",
            s3_key=key,
            sha256=stored.sha256,
            size=stored.size,
        )
        await emit(
            svc, state.run_id, RunEventType.artifact_created, ref.model_dump(mode="json"), "engine"
        )
        for check in result.checks:
            kind = {
                CheckStatus.pass_: RunEventType.check_passed,
                CheckStatus.warn: RunEventType.check_warned,
                CheckStatus.fail: RunEventType.check_failed,
            }[check.status]
            await emit(svc, state.run_id, kind, check.model_dump(mode="json"), "engine")
        if any(c.status == CheckStatus.fail for c in result.checks):
            raise VerificationFailed(f"{echo.name} verifier failed")
        return {
            "artifacts": [ref.model_dump(mode="json")],
            "checks": [c.model_dump(mode="json") for c in result.checks],
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

    g = StateGraph(BuildState)
    for name, fn in [
        ("intake", intake),
        ("spec", spec),
        ("create_version", create_version),
        ("engine", engine),
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
    g.add_edge("create_version", "engine")
    g.add_edge("engine", "finish")
    g.add_edge("finish", END)
    return g.compile(checkpointer=checkpointer)
