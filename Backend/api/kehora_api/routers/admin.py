"""/v1/admin/* (PRD 8.13): staff-only (users.role admin|support). Phase 0 is read-only lists;
mutating admin actions added later must write audit_log."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select

from kehora_api.deps import Session, Staff
from kehora_api.pagination import Page, PageParams, next_cursor, page_params
from kehora_db.enums import RunStatus
from kehora_db.models import AgentRun, Project, User

router = APIRouter(prefix="/admin", tags=["admin"])
Pages = Annotated[PageParams, Depends(page_params)]


class AdminUser(BaseModel):
    id: uuid.UUID
    clerk_id: str
    email: str | None
    name: str | None
    role: str
    created_at: datetime
    deleted_at: datetime | None


class AdminProject(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    kind: str | None
    visibility: str
    created_at: datetime


class AdminRun(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    org_id: uuid.UUID
    created_by_id: uuid.UUID
    status: str
    cost_minor: int
    cost_currency: str
    error: str | None
    created_at: datetime
    finished_at: datetime | None


@router.get("/users")
async def list_users(_: Staff, session: Session, page: Pages) -> Page[AdminUser]:
    stmt = select(User)
    if page.cursor:
        stmt = stmt.where(User.id < page.cursor)
    rows = list(await session.scalars(stmt.order_by(User.id.desc()).limit(page.limit + 1)))
    return Page[AdminUser](
        items=[AdminUser.model_validate(u, from_attributes=True) for u in rows[: page.limit]],
        next_cursor=next_cursor([u.id for u in rows], page.limit),
    )


@router.get("/projects")
async def list_projects(_: Staff, session: Session, page: Pages) -> Page[AdminProject]:
    stmt = select(Project)
    if page.cursor:
        stmt = stmt.where(Project.id < page.cursor)
    rows = list(await session.scalars(stmt.order_by(Project.id.desc()).limit(page.limit + 1)))
    return Page[AdminProject](
        items=[AdminProject.model_validate(p, from_attributes=True) for p in rows[: page.limit]],
        next_cursor=next_cursor([p.id for p in rows], page.limit),
    )


@router.get("/runs")
async def list_runs(
    _: Staff,
    session: Session,
    page: Pages,
    status: Annotated[RunStatus | None, Query()] = None,
) -> Page[AdminRun]:
    stmt = select(AgentRun)
    if status:
        stmt = stmt.where(AgentRun.status == status)
    if page.cursor:
        stmt = stmt.where(AgentRun.id < page.cursor)
    rows = list(await session.scalars(stmt.order_by(AgentRun.id.desc()).limit(page.limit + 1)))
    return Page[AdminRun](
        items=[AdminRun.model_validate(r, from_attributes=True) for r in rows[: page.limit]],
        next_cursor=next_cursor([r.id for r in rows], page.limit),
    )
