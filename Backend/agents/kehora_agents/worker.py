"""ARQ worker: `arq kehora_agents.worker.WorkerSettings`.

Jobs:
- `execute_run(run_id)`: enqueued by the API on project creation and on approval decisions.
- `recover_runs` (cron, every 5 s): re-enqueues runs that are queued/running with no live
  lease (their worker died) and gate-paused runs whose decision was stored but not applied.
"""

import contextlib
import os
import uuid
from datetime import timedelta
from typing import Any, ClassVar

import sentry_sdk
from arq import Retry, cron
from arq.connections import RedisSettings
from arq.worker import func
from sqlalchemy import select

from kehora_agents.checkpointer import open_checkpointer
from kehora_agents.graph import build_graph
from kehora_agents.runs import execute_run, lease_key, run_lease
from kehora_agents.services import Services
from kehora_common.clock import utcnow
from kehora_common.events import EXECUTE_RUN_JOB, RUN_QUEUE
from kehora_common.logging import configure_logging, get_logger
from kehora_common.settings import Environment, get_settings
from kehora_common.storage import Storage
from kehora_db.enums import ApprovalStatus, RunStatus
from kehora_db.models import AgentRun, Approval
from kehora_db.session import make_engine, make_sessionmaker
from kehora_engines_runner.runner import build_sandbox
from kehora_llm.gateway import build_gateway

log = get_logger(__name__)

QUEUE = RUN_QUEUE
STALE_AFTER = timedelta(seconds=15)


def configure_tracing(api_key: str | None, project: str) -> None:
    """LangSmith traces every LangGraph run when a key is configured."""
    if api_key:
        os.environ.setdefault("LANGSMITH_TRACING", "true")
        os.environ.setdefault("LANGSMITH_API_KEY", api_key)
        os.environ.setdefault("LANGSMITH_PROJECT", project)


async def startup(ctx: dict[str, Any]) -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.env)
    configure_tracing(
        settings.langsmith_api_key.get_secret_value() if settings.langsmith_api_key else None,
        settings.langsmith_project,
    )
    engine = make_engine(settings.database_url)
    storage = Storage(settings)
    if settings.env in (Environment.DEV, Environment.TEST):
        storage.ensure_bucket()
    svc = Services(
        settings=settings,
        sessionmaker=make_sessionmaker(engine),
        redis=ctx["redis"],
        gateway=build_gateway(settings),
        sandbox=build_sandbox(settings),
        storage=storage,
    )
    stack = contextlib.AsyncExitStack()
    saver = await stack.enter_async_context(open_checkpointer(settings.database_url))
    ctx.update(svc=svc, graph=build_graph(svc, saver), stack=stack, engine=engine)
    log.info("worker_started", llm_profile=settings.llm_routing_profile, sandbox=svc.sandbox.name)
    await recover_runs(ctx)


async def shutdown(ctx: dict[str, Any]) -> None:
    if "stack" in ctx:
        await ctx["stack"].aclose()
    if "engine" in ctx:
        await ctx["engine"].dispose()


async def execute_run_job(ctx: dict[str, Any], run_id: str) -> str:
    svc: Services = ctx["svc"]
    rid = uuid.UUID(run_id)
    async with run_lease(svc.redis, rid) as held:
        if not held:
            # Another worker is on it; try again shortly so a decision stored meanwhile
            # is not lost when that worker finishes.
            raise Retry(defer=2)
        return await execute_run(svc, ctx["graph"], rid)


async def recover_runs(ctx: dict[str, Any]) -> list[uuid.UUID]:
    svc: Services = ctx["svc"]
    cutoff = utcnow() - STALE_AFTER
    async with svc.sessionmaker() as session:
        stale = list(
            await session.scalars(
                select(AgentRun.id).where(
                    AgentRun.status.in_([RunStatus.QUEUED, RunStatus.RUNNING]),
                    AgentRun.updated_at < cutoff,
                )
            )
        )
        decided = list(
            await session.scalars(
                select(AgentRun.id)
                .join(Approval, Approval.run_id == AgentRun.id)
                .where(
                    AgentRun.status == RunStatus.AWAITING_APPROVAL,
                    Approval.status != ApprovalStatus.PENDING,
                )
            )
        )
    recovered: list[uuid.UUID] = []
    for run_id in {*stale, *decided}:
        if await svc.redis.exists(lease_key(run_id)):
            continue
        await ctx["redis"].enqueue_job(
            EXECUTE_RUN_JOB,
            str(run_id),
            _job_id=f"recover:{run_id}:{uuid.uuid4().hex[:8]}",
            _queue_name=QUEUE,
        )
        log.info("run_recovered", run_id=str(run_id))
        recovered.append(run_id)
    return recovered


async def recover_runs_cron(ctx: dict[str, Any]) -> None:
    await recover_runs(ctx)


def _redis_settings() -> RedisSettings:
    return RedisSettings.from_dsn(get_settings().redis_url)


class WorkerSettings:
    queue_name = QUEUE
    functions: ClassVar[list[Any]] = [
        func(execute_run_job, name=EXECUTE_RUN_JOB, timeout=900, max_tries=100)
    ]
    cron_jobs: ClassVar[list[Any]] = [
        cron(recover_runs_cron, name="recover_runs", second=set(range(0, 60, 5)))
    ]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = _redis_settings()
    max_jobs = 10
    job_timeout = 900
    keep_result = 60
