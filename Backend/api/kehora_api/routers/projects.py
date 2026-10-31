"""Projects and runs (PRD 10): create from a prompt, list, view, stream run events, approve."""

import json
import uuid
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sse_starlette.sse import EventSourceResponse

from kehora_api.deps import Auth, Session, State
from kehora_api.idempotency import Idem
from kehora_api.pagination import Page, PageParams, next_cursor, page_params
from kehora_api.services.access import member_org_ids, personal_org_id, require_org_role
from kehora_api.sse import run_events
from kehora_common.clock import utcnow
from kehora_common.events import EXECUTE_RUN_JOB, RUN_QUEUE
from kehora_common.logging import get_logger
from kehora_db.enums import ApprovalGate, ApprovalStatus, MemberRole, RunStatus
from kehora_db.models import AgentRun, Approval, Artifact, Check, Project, ProjectVersion

router = APIRouter(tags=["projects"])
log = get_logger(__name__)


# --- shapes --------------------------------------------------------------------------------
class RunOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    status: RunStatus
    trigger_prompt: str
    cost_minor: int
    cost_currency: str
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def of(cls, run: AgentRun) -> "RunOut":
        return cls.model_validate(run, from_attributes=True)


class ProjectOut(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    title: str
    kind: str | None
    visibility: str
    current_version_id: uuid.UUID | None
    created_at: datetime
    latest_run: RunOut | None = None


class ArtifactOut(BaseModel):
    id: uuid.UUID
    name: str = Field(description="File name, e.g. part.stl.")
    type: str
    format: str
    size: int
    sha256: str
    created_at: datetime

    @classmethod
    def of(cls, a: Artifact) -> "ArtifactOut":
        return cls(
            id=a.id,
            name=a.s3_key.rsplit("/", 1)[-1],
            type=a.type,
            format=a.format,
            size=a.size,
            sha256=a.sha256,
            created_at=a.created_at,
        )


class CheckOut(BaseModel):
    """A verifier result on one of the version's artifacts. For `printability/printable` the
    report is a full PrintabilityReport (Backend/schemas/printability.schema.json)."""

    id: uuid.UUID
    artifact_id: uuid.UUID | None
    engine: str
    name: str
    status: str
    report: dict[str, Any]


class VersionOut(BaseModel):
    id: uuid.UUID
    number: int
    spec: dict[str, Any]
    created_at: datetime
    artifacts: list[ArtifactOut]
    checks: list[CheckOut] = Field(default_factory=list)


class ProjectDetail(ProjectOut):
    current_version: VersionOut | None
    runs: list[RunOut]


class CreateProject(BaseModel):
    prompt: Annotated[str, Field(min_length=1, max_length=4000)]
    org_id: uuid.UUID | None = None


class ProjectCreated(BaseModel):
    project: ProjectOut
    run: RunOut


class GateName(StrEnum):
    SPEC = "spec"
    ORDER = "order"


class Decision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


class ApprovalIn(BaseModel):
    decision: Decision
    notes: Annotated[str | None, Field(max_length=2000)] = None


class ApprovalOut(BaseModel):
    id: uuid.UUID
    run_id: uuid.UUID
    gate: str
    status: str
    decided_at: datetime | None
    notes: str | None


# --- helpers ---------------------------------------------------------------------------------
def _project_out(project: Project, latest: AgentRun | None) -> ProjectOut:
    out = ProjectOut.model_validate(project, from_attributes=True)
    out.latest_run = RunOut.of(latest) if latest else None
    return out


async def _latest_runs(session: Session, project_ids: list[uuid.UUID]) -> dict[uuid.UUID, AgentRun]:
    if not project_ids:
        return {}
    rows = await session.scalars(
        select(AgentRun)
        .where(AgentRun.project_id.in_(project_ids))
        .order_by(AgentRun.project_id, AgentRun.created_at.desc())
        .ext(distinct_on(AgentRun.project_id))
    )
    return {r.project_id: r for r in rows}


async def _enqueue(state: State, run_id: uuid.UUID, reason: str) -> None:
    """Best effort: if Redis is down the worker's recovery cron picks the run up."""
    try:
        await state.extras["arq"].enqueue_job(
            EXECUTE_RUN_JOB,
            str(run_id),
            _job_id=f"{reason}:{run_id}:{uuid.uuid4().hex[:8]}",
            _queue_name=RUN_QUEUE,
        )
    except Exception as exc:
        log.warning("enqueue_failed", run_id=str(run_id), error=str(exc))


async def _run_for_member(
    session: Session, auth: Auth, run_id: uuid.UUID, minimum: MemberRole
) -> AgentRun:
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    await require_org_role(session, auth.user, run.org_id, minimum)
    return run


# --- projects --------------------------------------------------------------------------------
@router.post("/projects", status_code=status.HTTP_201_CREATED, response_model=ProjectCreated)
async def create_project(
    body: CreateProject, auth: Auth, session: Session, state: State, idem: Idem
) -> ProjectCreated | JSONResponse:
    if (replayed := await idem.replay()) is not None:
        return replayed
    org_id = body.org_id or await personal_org_id(session, auth.user)
    await require_org_role(session, auth.user, org_id, MemberRole.MEMBER)
    prompt = body.prompt.strip()
    title = prompt.splitlines()[0][:80] or "New project"
    project = Project(org_id=org_id, owner_id=auth.user.id, title=title)
    session.add(project)
    await session.flush()
    run = AgentRun(
        project_id=project.id, org_id=org_id, created_by_id=auth.user.id, trigger_prompt=prompt
    )
    session.add(run)
    await session.flush()
    await session.refresh(project)
    await session.refresh(run)
    result = ProjectCreated(project=_project_out(project, run), run=RunOut.of(run))
    await idem.complete(session, status.HTTP_201_CREATED, result)
    await session.commit()
    await _enqueue(state, run.id, "start")
    return result


@router.get("/projects")
async def list_projects(
    auth: Auth, session: Session, page: Annotated[PageParams, Depends(page_params)]
) -> Page[ProjectOut]:
    stmt = select(Project).where(Project.org_id.in_(await member_org_ids(session, auth.user)))
    if page.cursor:
        stmt = stmt.where(Project.id < page.cursor)
    rows = list(await session.scalars(stmt.order_by(Project.id.desc()).limit(page.limit + 1)))
    latest = await _latest_runs(session, [p.id for p in rows[: page.limit]])
    return Page[ProjectOut](
        items=[_project_out(p, latest.get(p.id)) for p in rows[: page.limit]],
        next_cursor=next_cursor([p.id for p in rows], page.limit),
    )


@router.get("/projects/{project_id}")
async def get_project(project_id: uuid.UUID, auth: Auth, session: Session) -> ProjectDetail:
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    await require_org_role(session, auth.user, project.org_id, MemberRole.VIEWER)
    runs = list(
        await session.scalars(
            select(AgentRun)
            .where(AgentRun.project_id == project.id)
            .order_by(AgentRun.created_at.desc())
            .limit(20)
        )
    )
    version_out = None
    if project.current_version_id:
        version = await session.get(ProjectVersion, project.current_version_id)
        assert version is not None
        artifacts = list(
            await session.scalars(
                select(Artifact)
                .where(Artifact.version_id == version.id)
                .order_by(Artifact.created_at)
            )
        )
        checks = await session.scalars(
            select(Check)
            .where(Check.artifact_id.in_([a.id for a in artifacts]))
            .order_by(Check.created_at)
        )
        version_out = VersionOut(
            id=version.id,
            number=version.number,
            spec=version.spec,
            created_at=version.created_at,
            artifacts=[ArtifactOut.of(a) for a in artifacts],
            checks=[CheckOut.model_validate(c, from_attributes=True) for c in checks],
        )
    base = _project_out(project, runs[0] if runs else None)
    return ProjectDetail(
        **base.model_dump(), current_version=version_out, runs=[RunOut.of(r) for r in runs]
    )


# --- runs ------------------------------------------------------------------------------------
@router.get("/runs/{run_id}", tags=["runs"])
async def get_run(run_id: uuid.UUID, auth: Auth, session: Session) -> RunOut:
    return RunOut.of(await _run_for_member(session, auth, run_id, MemberRole.VIEWER))


@router.get(
    "/runs/{run_id}/events",
    tags=["runs"],
    response_class=EventSourceResponse,
    responses={200: {"content": {"text/event-stream": {}}, "description": "RunEvent stream"}},
)
async def stream_run_events(
    run_id: uuid.UUID,
    request: Request,
    auth: Auth,
    session: Session,
    state: State,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
    after: Annotated[int | None, Query(ge=0, description="Alternative to Last-Event-ID")] = None,
) -> EventSourceResponse:
    """Server-sent RunEvents (`id` = seq, `event` = type, `data` = RunEvent JSON)."""
    await _run_for_member(session, auth, run_id, MemberRole.VIEWER)
    try:
        last = int(last_event_id) if last_event_id else (after or 0)
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "bad Last-Event-ID") from None
    await session.close()  # don't hold a DB connection for the life of the stream

    async def frames() -> Any:
        async for event in run_events(
            state.sessionmaker, state.extras["redis"], run_id, last, request.is_disconnected
        ):
            yield {"id": str(event["seq"]), "event": event["type"], "data": json.dumps(event)}

    return EventSourceResponse(frames(), ping=15, headers={"Cache-Control": "no-store"})


@router.post(
    "/runs/{run_id}/approvals/{gate}",
    tags=["runs"],
    response_model=ApprovalOut,
)
async def decide_approval(
    run_id: uuid.UUID,
    gate: GateName,
    body: ApprovalIn,
    auth: Auth,
    session: Session,
    state: State,
    idem: Idem,
) -> ApprovalOut | JSONResponse:
    if (replayed := await idem.replay()) is not None:
        return replayed
    if gate != GateName.SPEC:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "the order gate arrives in phase 4")
    run = await _run_for_member(session, auth, run_id, MemberRole.MEMBER)
    approval = await session.scalar(
        select(Approval)
        .where(
            Approval.run_id == run.id,
            Approval.gate == ApprovalGate.SPEC,
            Approval.status == ApprovalStatus.PENDING,
        )
        .with_for_update()
    )
    if approval is None or run.status != RunStatus.AWAITING_APPROVAL:
        raise HTTPException(status.HTTP_409_CONFLICT, "run is not waiting for spec approval")
    approval.status = (
        ApprovalStatus.APPROVED if body.decision == Decision.APPROVE else ApprovalStatus.REJECTED
    )
    approval.decided_by = auth.user.id
    approval.decided_at = utcnow()
    approval.notes = body.notes
    await session.flush()
    result = ApprovalOut.model_validate(approval, from_attributes=True)
    await idem.complete(session, status.HTTP_200_OK, result)
    await session.commit()
    await _enqueue(state, run.id, "approval")
    return result
