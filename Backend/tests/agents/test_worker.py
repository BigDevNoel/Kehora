from datetime import timedelta
from typing import Any

import pytest
from arq import Retry
from arq.connections import ArqRedis
from sqlalchemy import update

from kehora_agents.runs import lease_key, run_lease
from kehora_agents.services import Services
from kehora_agents.worker import execute_run_job, recover_runs
from kehora_common.clock import utcnow
from kehora_common.events import RUN_QUEUE
from kehora_db.models import AgentRun, Approval

pytestmark = [pytest.mark.db, pytest.mark.redis]


async def _age(svc: Services, run: AgentRun, status: str) -> None:
    async with svc.sessionmaker() as s, s.begin():
        await s.execute(
            update(AgentRun)
            .where(AgentRun.id == run.id)
            .values(status=status, updated_at=utcnow() - timedelta(minutes=1))
        )


def _ctx(svc: Services) -> dict[str, Any]:
    return {"svc": svc, "redis": ArqRedis(connection_pool=svc.redis.connection_pool)}


async def test_recovery_enqueues_orphaned_runs_but_not_leased_ones(
    svc: Services, run: AgentRun
) -> None:
    await _age(svc, run, "running")
    ctx = _ctx(svc)
    await svc.redis.set(lease_key(run.id), "someone-else", px=10_000)
    assert run.id not in await recover_runs(ctx)

    await svc.redis.delete(lease_key(run.id))
    assert run.id in await recover_runs(ctx)
    assert await svc.redis.zcard(RUN_QUEUE) >= 1


async def test_recovery_applies_stored_decisions(svc: Services, run: AgentRun) -> None:
    async with svc.sessionmaker() as s, s.begin():
        s.add(Approval(run_id=run.id, gate="spec", status="approved", decided_at=utcnow()))
        await s.execute(
            update(AgentRun).where(AgentRun.id == run.id).values(status="awaiting_approval")
        )
    assert run.id in await recover_runs(_ctx(svc))


async def test_fresh_runs_are_left_alone(svc: Services, run: AgentRun) -> None:
    assert run.id not in await recover_runs(_ctx(svc))  # queued but just created


async def test_job_retries_when_another_worker_holds_the_lease(
    svc: Services, run: AgentRun
) -> None:
    async with run_lease(svc.redis, run.id) as held:
        assert held
        with pytest.raises(Retry):
            await execute_run_job({"svc": svc, "graph": None}, str(run.id))
    assert not await svc.redis.exists(lease_key(run.id))
