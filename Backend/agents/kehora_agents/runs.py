"""Executing a run: start, continue after a crash, or resume after an approval (ADR-0009).

There is one entry point, `execute_run(run_id)`. It works out what to do from the run row, the
LangGraph checkpoint and the `approvals` table, so it is safe to call any number of times:
- no checkpoint yet          -> start the graph from the prompt;
- paused at a gate, decided  -> resume with the stored decision;
- paused at a gate, pending  -> nothing to do;
- checkpoint mid-graph       -> continue from the last completed node (crash recovery).
A Redis lease ensures only one worker executes a given run at a time.
"""

import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from typing import Any

from langgraph.types import Command
from redis.asyncio import Redis
from sqlalchemy import select

from kehora_agents.graph import PolicyRefusal
from kehora_agents.services import Services, emit, set_status
from kehora_common.clock import utcnow
from kehora_common.logging import get_logger
from kehora_db.enums import ApprovalGate, ApprovalStatus, RunStatus
from kehora_db.models import AgentRun, Approval, Project
from kehora_schemas import RunEventType

log = get_logger(__name__)

LEASE_TTL_MS = 10_000
LEASE_REFRESH_S = 3.0
TERMINAL = {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}


def lease_key(run_id: uuid.UUID | str) -> str:
    return f"run:{run_id}:lease"


@contextlib.asynccontextmanager
async def run_lease(redis: Redis, run_id: uuid.UUID) -> AsyncIterator[bool]:
    key, token = lease_key(run_id), uuid.uuid4().hex
    acquired = bool(await redis.set(key, token, nx=True, px=LEASE_TTL_MS))
    if not acquired:
        yield False
        return

    async def refresh() -> None:
        while True:
            await asyncio.sleep(LEASE_REFRESH_S)
            if (await redis.get(key)) not in (token, token.encode()):
                log.warning("run_lease_lost", run_id=str(run_id))
                return
            await redis.pexpire(key, LEASE_TTL_MS)

    task = asyncio.create_task(refresh())
    try:
        yield True
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        if (await redis.get(key)) in (token, token.encode()):
            await redis.delete(key)


async def _decision(svc: Services, run_id: uuid.UUID) -> dict[str, Any] | None:
    async with svc.sessionmaker() as session:
        approval = await session.scalar(
            select(Approval)
            .where(Approval.run_id == run_id, Approval.gate == ApprovalGate.SPEC)
            .order_by(Approval.created_at.desc())
            .limit(1)
        )
    if approval is None or approval.status == ApprovalStatus.PENDING:
        return None
    return {"approved": approval.status == ApprovalStatus.APPROVED, "notes": approval.notes}


async def fail_run(
    svc: Services, run_id: uuid.UUID, reason: str, *, status: str = RunStatus.FAILED
) -> None:
    await set_status(svc, run_id, status, finished_at=utcnow(), error=reason[:2000])
    await emit(svc, run_id, RunEventType.run_failed, {"reason": reason[:2000], "status": status})


async def execute_run(svc: Services, graph: Any, run_id: uuid.UUID) -> str:
    """Advance the run as far as it can go. Returns the run status afterwards."""
    async with svc.sessionmaker() as session:
        run = await session.get(AgentRun, run_id)
        if run is None:
            log.warning("run_missing", run_id=str(run_id))
            return "missing"
        if run.status in TERMINAL:
            return run.status
        project = await session.get(Project, run.project_id)
        assert project is not None
        initial = {
            "run_id": str(run.id),
            "project_id": str(run.project_id),
            "org_id": str(project.org_id),
            "prompt": run.trigger_prompt,
        }
        first_start = run.started_at is None

    config: dict[str, Any] = {
        "configurable": {"thread_id": str(run_id)},
        "run_name": "kehora-build",
        "metadata": {"run_id": str(run_id), "project_id": initial["project_id"]},
    }

    while True:
        snapshot = await graph.aget_state(config)
        inp: Any
        if not snapshot.values:
            inp = initial
        elif snapshot.next:
            paused = any(t.interrupts for t in snapshot.tasks)
            if paused:
                decision = await _decision(svc, run_id)
                if decision is None:
                    await set_status(svc, run_id, RunStatus.AWAITING_APPROVAL)
                    return RunStatus.AWAITING_APPROVAL
                inp = Command(resume=decision)
            else:
                inp = None  # continue after a crash
        else:
            break  # graph already completed

        if first_start:
            await set_status(svc, run_id, RunStatus.RUNNING, started_at=utcnow())
            await emit(svc, run_id, RunEventType.run_started, {"prompt": initial["prompt"]})
            first_start = False
        else:
            await set_status(svc, run_id, RunStatus.RUNNING)

        try:
            await graph.ainvoke(inp, config)
        except PolicyRefusal as exc:
            await fail_run(svc, run_id, f"Request declined: {exc}", status=RunStatus.CANCELLED)
            return RunStatus.CANCELLED
        except Exception as exc:
            log.exception("run_failed", run_id=str(run_id))
            await fail_run(svc, run_id, f"{type(exc).__name__}: {exc}")
            return RunStatus.FAILED
        # Loop: the graph either finished or paused at a gate; a decision may already exist.

    final = await graph.aget_state(config)
    if final.values.get("spec_approved") is False:
        await fail_run(svc, run_id, "Spec rejected by user", status=RunStatus.CANCELLED)
        return RunStatus.CANCELLED
    async with svc.sessionmaker() as session:
        run = await session.get(AgentRun, run_id)
        assert run is not None
        return run.status
