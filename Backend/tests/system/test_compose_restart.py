"""Phase 0 gate, system level: a run survives killing the worker container mid-node.

Runs against the docker compose stack (`make e2e` starts it with LLM_ROUTING_PROFILE=test and
ECHO_DELAY_S so the engine node is slow enough to interrupt). Seeds a run directly in Postgres,
so it needs no Clerk credentials; the Playwright suite covers the same flow through the UI.
"""

import asyncio
import subprocess
import time
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kehora_common.clock import utcnow
from kehora_common.events import EXECUTE_RUN_JOB, RUN_QUEUE
from kehora_db.models import (
    AgentRun,
    Approval,
    Artifact,
    Organization,
    Project,
    ProjectVersion,
    RunEventRow,
    User,
)
from kehora_db.session import make_engine, make_sessionmaker

pytestmark = pytest.mark.system

REPO = Path(__file__).resolve().parents[3]
DB_URL = "postgresql+psycopg://kehora:kehora@localhost:5432/kehora"
REDIS_URL = "redis://localhost:6379/0"


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], cwd=REPO, check=True, capture_output=True)  # noqa: S603, S607


@pytest.fixture
async def sm() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = make_engine(DB_URL)
    yield make_sessionmaker(engine)
    await engine.dispose()


async def _enqueue(run_id: uuid.UUID) -> None:
    pool = await create_pool(RedisSettings.from_dsn(REDIS_URL))
    await pool.enqueue_job(
        EXECUTE_RUN_JOB, str(run_id), _job_id=f"system:{uuid.uuid4().hex}", _queue_name=RUN_QUEUE
    )
    await pool.aclose()


async def _wait(
    sm: async_sessionmaker[AsyncSession], run_id: uuid.UUID, cond: str, within: float
) -> None:
    deadline = time.monotonic() + within
    while time.monotonic() < deadline:
        async with sm() as s:
            run = await s.get(AgentRun, run_id)
            assert run is not None
            types = list(
                await s.scalars(select(RunEventRow.type).where(RunEventRow.run_id == run_id))
            )
            nodes = list(
                await s.scalars(
                    select(RunEventRow.node).where(
                        RunEventRow.run_id == run_id, RunEventRow.type == "node_started"
                    )
                )
            )
        if cond == "engine_started" and "engine" in nodes:
            return
        if cond == run.status:
            return
        if run.status in ("failed", "cancelled"):
            raise AssertionError(f"run ended as {run.status}: {run.error}; events {types}")
        await asyncio.sleep(0.5)
    raise AssertionError(f"timed out waiting for {cond}; events {types}")


async def test_run_survives_worker_kill_mid_engine(sm: async_sessionmaker[AsyncSession]) -> None:
    async with sm() as s, s.begin():
        user = User(clerk_id=f"user_system_{uuid.uuid4().hex}")
        org = Organization(name="System test", type="personal")
        s.add_all([user, org])
        await s.flush()
        project = Project(org_id=org.id, owner_id=user.id, title="Restart gate")
        s.add(project)
        await s.flush()
        run = AgentRun(
            project_id=project.id,
            org_id=org.id,
            created_by_id=user.id,
            trigger_prompt="A small cable clip for a desk edge",
        )
        s.add(run)
    await _enqueue(run.id)
    await _wait(sm, run.id, "awaiting_approval", 60)

    async with sm() as s, s.begin():
        approval = await s.scalar(select(Approval).where(Approval.run_id == run.id))
        assert approval is not None
        approval.status, approval.decided_at = "approved", utcnow()
    await _enqueue(run.id)
    await _wait(sm, run.id, "engine_started", 60)

    compose("kill", "worker")
    async with sm() as s:
        killed = await s.get(AgentRun, run.id)
        assert killed is not None and killed.status == "running"
    compose("start", "worker")  # same container and config, like a process restart

    await _wait(sm, run.id, "succeeded", 120)

    async with sm() as s:
        events = list(
            await s.scalars(
                select(RunEventRow).where(RunEventRow.run_id == run.id).order_by(RunEventRow.seq)
            )
        )
        seqs = [e.seq for e in events]
        types = [e.type for e in events]
        assert seqs == list(range(1, len(seqs) + 1)), "duplicate or missing seq"
        assert types.count("run_started") == 1
        assert types.count("run_finished") == 1
        assert [e.node for e in events if e.type == "node_started"].count("engine") == 2
        versions = await s.scalar(
            select(func.count())
            .select_from(ProjectVersion)
            .where(ProjectVersion.created_by_run_id == run.id)
        )
        assert versions == 1
        version_id = await s.scalar(select(AgentRun.version_id).where(AgentRun.id == run.id))
        artifacts = await s.scalar(
            select(func.count()).select_from(Artifact).where(Artifact.version_id == version_id)
        )
        assert artifacts == 1
