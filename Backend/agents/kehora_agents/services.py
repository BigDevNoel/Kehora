"""Everything a run needs, built once per worker process."""

import json
import uuid
from dataclasses import dataclass
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kehora_common.clock import utcnow
from kehora_common.events import STREAM_MAXLEN, stream_id, stream_key
from kehora_common.logging import get_logger
from kehora_common.settings import Settings
from kehora_common.storage import Storage
from kehora_db.models import AgentRun, RunEventRow
from kehora_engines_runner.sandbox import SandboxProvider
from kehora_llm.gateway import Gateway, UsageSink
from kehora_llm.types import UsageRecord
from kehora_schemas import RunEventType

log = get_logger(__name__)


@dataclass
class Services:
    settings: Settings
    sessionmaker: async_sessionmaker[AsyncSession]
    redis: Redis
    gateway: Gateway
    sandbox: SandboxProvider
    storage: Storage


async def emit(
    svc: Services,
    run_id: uuid.UUID,
    type_: RunEventType,
    payload: dict[str, Any] | None = None,
    node: str | None = None,
) -> int:
    """Append an event: Postgres first (source of truth, seq assigned under a row lock on the
    run), then the Redis stream for live SSE. Returns the seq."""
    body = payload or {}
    async with svc.sessionmaker() as session, session.begin():
        await session.execute(select(AgentRun.id).where(AgentRun.id == run_id).with_for_update())
        last = await session.scalar(
            select(func.coalesce(func.max(RunEventRow.seq), 0)).where(RunEventRow.run_id == run_id)
        )
        seq = int(last or 0) + 1
        row = RunEventRow(run_id=run_id, seq=seq, type=type_.value, node=node, payload=body)
        session.add(row)
        await session.flush()
        created_at = row.created_at
    event = {
        "run_id": str(run_id),
        "seq": seq,
        "type": type_.value,
        "node": node,
        "payload": body,
        "created_at": created_at.isoformat(),
    }
    try:
        await svc.redis.xadd(
            stream_key(run_id),
            {"event": json.dumps(event, default=str)},
            id=stream_id(seq),
            maxlen=STREAM_MAXLEN,
            approximate=True,
        )
    except Exception as exc:  # SSE readers backfill gaps from Postgres
        log.warning("event_stream_publish_failed", run_id=str(run_id), seq=seq, error=str(exc))
    return seq


async def set_status(svc: Services, run_id: uuid.UUID, status: str, **fields: Any) -> None:
    async with svc.sessionmaker() as session, session.begin():
        await session.execute(
            update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(status=status, updated_at=utcnow(), **fields)
        )


def usage_sink(svc: Services, run_id: uuid.UUID) -> UsageSink:
    """Gateway sink: append the call to agent_runs.model_usage, roll cost into cost_minor
    (USD cents, rounded up; ADR-0007) and emit cost_update."""

    async def record(rec: UsageRecord) -> None:
        async with svc.sessionmaker() as session, session.begin():
            run = await session.get(AgentRun, run_id, with_for_update=True)
            if run is None:
                return
            usage = dict(run.model_usage or {})
            calls = [*usage.get("calls", []), rec.model_dump(mode="json")]
            total_micros = sum(c.get("cost_usd_micros") or 0 for c in calls)
            usage.update(
                calls=calls,
                total_usd_micros=total_micros,
                input_tokens=sum(c["usage"]["input_tokens"] for c in calls),
                output_tokens=sum(c["usage"]["output_tokens"] for c in calls),
            )
            run.model_usage = usage
            run.cost_minor = -(-total_micros // 10_000)
            run.cost_currency = "USD"
            cost_minor = run.cost_minor
        await emit(
            svc,
            run_id,
            RunEventType.cost_update,
            {
                "cost_minor": cost_minor,
                "currency": "USD",
                "total_usd_micros": total_micros,
                "model": rec.model,
                "role": rec.role,
            },
        )

    return record
