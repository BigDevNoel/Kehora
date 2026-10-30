"""Run event stream for SSE (ADR-0009): replay from Postgres after Last-Event-ID, then tail the
Redis stream from exactly that seq, backfilling any gap from Postgres. Ends after a terminal
event."""

import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kehora_common.events import TERMINAL_EVENTS, seq_from_stream_id, stream_id, stream_key
from kehora_db.models import RunEventRow

BLOCK_MS = 15_000


def _row_event(row: RunEventRow) -> dict[str, Any]:
    return {
        "run_id": str(row.run_id),
        "seq": row.seq,
        "type": row.type,
        "node": row.node,
        "payload": row.payload,
        "created_at": row.created_at.isoformat(),
    }


async def _from_db(
    sessionmaker: async_sessionmaker[AsyncSession],
    run_id: uuid.UUID,
    after: int,
    upto: int | None = None,
) -> list[dict[str, Any]]:
    async with sessionmaker() as session:
        stmt = select(RunEventRow).where(RunEventRow.run_id == run_id, RunEventRow.seq > after)
        if upto is not None:
            stmt = stmt.where(RunEventRow.seq < upto)
        rows = await session.scalars(stmt.order_by(RunEventRow.seq))
        return [_row_event(r) for r in rows]


async def run_events(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    run_id: uuid.UUID,
    last_seq: int,
    is_disconnected: Callable[[], Awaitable[bool]],
    block_ms: int = BLOCK_MS,
) -> AsyncIterator[dict[str, Any]]:
    """Yield RunEvent dicts in seq order, each exactly once, starting after `last_seq`."""
    last = last_seq

    for event in await _from_db(sessionmaker, run_id, last):
        last = event["seq"]
        yield event
        if event["type"] in TERMINAL_EVENTS:
            return

    key = stream_key(run_id)
    while not await is_disconnected():
        response = await redis.xread({key: stream_id(last)}, count=100, block=block_ms)
        if not response:
            # Quiet period: pick up anything whose Redis publish was lost.
            for event in await _from_db(sessionmaker, run_id, last):
                last = event["seq"]
                yield event
                if event["type"] in TERMINAL_EVENTS:
                    return
            continue
        for entry_id, fields in response[0][1]:
            seq = seq_from_stream_id(entry_id)
            if seq <= last:
                continue
            if seq > last + 1:
                for event in await _from_db(sessionmaker, run_id, last, upto=seq):
                    last = event["seq"]
                    yield event
            raw = fields.get(b"event") or fields.get("event")
            event = json.loads(raw)
            last = seq
            yield event
            if event["type"] in TERMINAL_EVENTS:
                return
