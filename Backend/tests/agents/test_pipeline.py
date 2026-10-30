"""The Phase 0 run pipeline end to end: fake LLM, real Postgres, Redis, S3 and Docker."""

import asyncio
import json
from typing import Any

import pytest
from sqlalchemy import select

from kehora_agents.runs import execute_run
from kehora_agents.services import Services
from kehora_common.clock import utcnow
from kehora_common.events import stream_key
from kehora_db.models import (
    AgentRun,
    Approval,
    Artifact,
    Check,
    Project,
    ProjectVersion,
    RunEventRow,
)
from kehora_engines.base import SandboxJob, SandboxResult
from kehora_llm.adapters.fake import FakeAdapter
from kehora_llm.types import Completion

pytestmark = [pytest.mark.db, pytest.mark.redis, pytest.mark.s3, pytest.mark.docker]


async def _events(svc: Services, run: AgentRun) -> list[RunEventRow]:
    async with svc.sessionmaker() as s:
        rows = await s.scalars(
            select(RunEventRow).where(RunEventRow.run_id == run.id).order_by(RunEventRow.seq)
        )
        return list(rows)


async def _types(svc: Services, run: AgentRun) -> list[str]:
    return [e.type for e in await _events(svc, run)]


async def _decide(svc: Services, run: AgentRun, status: str) -> None:
    async with svc.sessionmaker() as s, s.begin():
        approval = await s.scalar(select(Approval).where(Approval.run_id == run.id))
        assert approval is not None and approval.status == "pending"
        approval.status = status
        approval.decided_at = utcnow()


async def _status(svc: Services, run: AgentRun) -> str:
    async with svc.sessionmaker() as s:
        row = await s.get(AgentRun, run.id)
        assert row is not None
        return row.status


async def test_run_pauses_for_spec_approval_then_finishes(
    svc: Services, graph: Any, run: AgentRun
) -> None:
    assert await execute_run(svc, graph, run.id) == "awaiting_approval"
    types = await _types(svc, run)
    assert types[0] == "run_started"
    assert types[-1] == "needs_approval"
    assert "cost_update" in types
    needs = (await _events(svc, run))[-1]
    assert needs.payload["gate"] == "spec"
    assert needs.payload["spec"]["schema_version"] == 0

    # Executing again while the decision is pending changes nothing.
    assert await execute_run(svc, graph, run.id) == "awaiting_approval"
    assert len(await _types(svc, run)) == len(types)

    await _decide(svc, run, "approved")
    assert await execute_run(svc, graph, run.id) == "succeeded"

    events = await _events(svc, run)
    assert [e.seq for e in events] == list(range(1, len(events) + 1))
    tail = [e.type for e in events[len(types) :]]
    assert "artifact_created" in tail and "check_passed" in tail
    assert tail[-1] == "run_finished"

    async with svc.sessionmaker() as s:
        version = await s.scalar(
            select(ProjectVersion).where(ProjectVersion.created_by_run_id == run.id)
        )
        assert version is not None and version.number == 1
        project = await s.get(Project, run.project_id)
        assert project is not None and project.current_version_id == version.id
        artifact = await s.scalar(select(Artifact).where(Artifact.version_id == version.id))
        assert artifact is not None
        check = await s.scalar(select(Check).where(Check.run_id == run.id))
        assert check is not None and check.status == "pass"
        finished = await s.get(AgentRun, run.id)
        assert finished is not None and finished.finished_at is not None
        assert finished.model_usage["calls"] and finished.cost_currency == "USD"
    stored = await asyncio.to_thread(svc.storage.get_bytes, artifact.s3_key)
    assert stored.decode().startswith(version.spec["title"])

    # Every event is mirrored on the Redis stream with id == seq.
    entries = await svc.redis.xrange(stream_key(run.id))
    assert [int(eid.split(b"-")[0]) for eid, _ in entries] == [e.seq for e in events]
    assert json.loads(entries[-1][1][b"event"])["type"] == "run_finished"

    # Terminal runs are left alone.
    assert await execute_run(svc, graph, run.id) == "succeeded"


async def test_crash_mid_engine_resumes_from_checkpoint(
    svc: Services, graph: Any, run: AgentRun
) -> None:
    await execute_run(svc, graph, run.id)
    await _decide(svc, run, "approved")

    real = svc.sandbox
    entered = asyncio.Event()

    class HangingSandbox:
        name = "hanging"

        async def run(self, job: SandboxJob) -> SandboxResult:
            entered.set()
            await asyncio.sleep(3600)
            raise AssertionError("unreachable")

    svc.sandbox = HangingSandbox()
    task = asyncio.create_task(execute_run(svc, graph, run.id))
    await asyncio.wait_for(entered.wait(), timeout=30)
    task.cancel()  # the worker process dies mid-node
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await _status(svc, run) == "running"

    svc.sandbox = real
    assert await execute_run(svc, graph, run.id) == "succeeded"

    events = await _events(svc, run)
    seqs = [e.seq for e in events]
    assert seqs == list(range(1, len(seqs) + 1))  # no duplicates, no gaps
    types = [e.type for e in events]
    assert types.count("run_finished") == 1
    assert types.count("run_started") == 1
    assert types.count("node_started") >= 5  # engine node started twice
    async with svc.sessionmaker() as s:
        versions = list(
            await s.scalars(
                select(ProjectVersion).where(ProjectVersion.created_by_run_id == run.id)
            )
        )
        assert len(versions) == 1
        artifacts = list(
            await s.scalars(select(Artifact).where(Artifact.version_id == versions[0].id))
        )
        assert len(artifacts) == 1


async def test_rejected_spec_cancels_run(svc: Services, graph: Any, run: AgentRun) -> None:
    await execute_run(svc, graph, run.id)
    await _decide(svc, run, "rejected")
    assert await execute_run(svc, graph, run.id) == "cancelled"
    events = await _events(svc, run)
    assert events[-1].type == "run_failed"
    assert events[-1].payload["status"] == "cancelled"
    assert "artifact_created" not in [e.type for e in events]


async def test_policy_refusal_cancels_at_intake(svc: Services, graph: Any, run: AgentRun) -> None:
    fake = svc.gateway.adapters["fake"]
    assert isinstance(fake, FakeAdapter)
    fake.scripted.append(
        Completion(
            provider="fake",
            model="fake-small",
            text=json.dumps(
                {
                    "kind": "object",
                    "decision": "refuse",
                    "reason": "Firearm parts.",
                    "policy_category": "weapons",
                }
            ),
        )
    )
    assert await execute_run(svc, graph, run.id) == "cancelled"
    last = (await _events(svc, run))[-1]
    assert last.type == "run_failed" and "Firearm parts." in last.payload["reason"]


async def test_failing_verifier_fails_run_and_never_finishes(
    svc: Services, graph: Any, run: AgentRun
) -> None:
    await execute_run(svc, graph, run.id)
    await _decide(svc, run, "approved")

    class LyingSandbox:
        name = "lying"

        async def run(self, job: SandboxJob) -> SandboxResult:
            return SandboxResult(exit_code=0, stdout="", stderr="", outputs={"echo.txt": b"wrong"})

    svc.sandbox = LyingSandbox()
    assert await execute_run(svc, graph, run.id) == "failed"
    types = await _types(svc, run)
    assert "check_failed" in types and "run_finished" not in types
    assert types[-1] == "run_failed"
