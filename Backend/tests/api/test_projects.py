import asyncio
import json
import uuid
from typing import Any

import httpx
import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kehora_api.sse import run_events
from kehora_common.events import RUN_QUEUE, stream_id, stream_key
from kehora_db.models import AgentRun, Approval, Membership, RunEventRow
from tests.api.fake_clerk import FakeClerk

pytestmark = [pytest.mark.db, pytest.mark.redis]


async def _user(
    client: httpx.AsyncClient, clerk: FakeClerk
) -> tuple[dict[str, str], dict[str, Any]]:
    data = clerk.add_user(f"{uuid.uuid4().hex[:8]}@example.com")
    headers = clerk.headers(data["id"])
    return headers, (await client.get("/v1/me", headers=headers)).json()


async def _create(
    client: httpx.AsyncClient, headers: dict[str, str], prompt: str = "A phone stand"
) -> dict[str, Any]:
    resp = await client.post("/v1/projects", json={"prompt": prompt}, headers=headers)
    assert resp.status_code == 201, resp.text
    body: dict[str, Any] = resp.json()
    return body


async def _await_approval(session: AsyncSession, run_id: str) -> None:
    run = await session.get(AgentRun, uuid.UUID(run_id))
    assert run is not None
    run.status = "awaiting_approval"
    session.add(Approval(run_id=run.id, gate="spec"))
    await session.commit()


async def test_create_project_starts_a_queued_run(
    client: httpx.AsyncClient, clerk: FakeClerk, redis: Redis
) -> None:
    headers, me = await _user(client, clerk)
    body = await _create(client, headers, "A desk stand for my phone\nwith a cable slot")
    assert body["project"]["title"] == "A desk stand for my phone"
    assert body["project"]["org_id"] == me["memberships"][0]["org_id"]
    assert body["run"]["status"] == "queued"
    assert body["project"]["latest_run"]["id"] == body["run"]["id"]
    assert await redis.zcard(RUN_QUEUE) == 1


async def test_create_project_is_idempotent(
    client: httpx.AsyncClient, clerk: FakeClerk, redis: Redis
) -> None:
    headers, _ = await _user(client, clerk)
    h = {**headers, "Idempotency-Key": "proj-1"}
    a = await client.post("/v1/projects", json={"prompt": "A hook"}, headers=h)
    b = await client.post("/v1/projects", json={"prompt": "A hook"}, headers=h)
    assert a.status_code == b.status_code == 201
    assert a.json()["project"]["id"] == b.json()["project"]["id"]
    assert await redis.zcard(RUN_QUEUE) == 1
    listed = (await client.get("/v1/projects", headers=headers)).json()
    assert len(listed["items"]) == 1


async def test_list_projects_is_scoped_and_paginated(
    client: httpx.AsyncClient, clerk: FakeClerk
) -> None:
    headers, _ = await _user(client, clerk)
    other, _ = await _user(client, clerk)
    ids = [(await _create(client, headers, f"Thing {i}"))["project"]["id"] for i in range(3)]
    await _create(client, other, "Not yours")

    first = (await client.get("/v1/projects?limit=2", headers=headers)).json()
    assert [p["id"] for p in first["items"]] == ids[::-1][:2]
    assert first["next_cursor"]
    second = (
        await client.get(f"/v1/projects?limit=2&cursor={first['next_cursor']}", headers=headers)
    ).json()
    assert [p["id"] for p in second["items"]] == [ids[0]]
    assert second["next_cursor"] is None


async def test_project_and_run_are_member_only(client: httpx.AsyncClient, clerk: FakeClerk) -> None:
    headers, _ = await _user(client, clerk)
    other, _ = await _user(client, clerk)
    body = await _create(client, headers)
    pid, rid = body["project"]["id"], body["run"]["id"]
    assert (await client.get(f"/v1/projects/{pid}", headers=headers)).status_code == 200
    assert (await client.get(f"/v1/projects/{pid}", headers=other)).status_code == 404
    assert (await client.get(f"/v1/runs/{rid}", headers=other)).status_code == 404
    assert (await client.get(f"/v1/runs/{rid}/events", headers=other)).status_code == 404
    detail = (await client.get(f"/v1/projects/{pid}", headers=headers)).json()
    assert detail["current_version"] is None and detail["runs"][0]["id"] == rid


async def test_approve_spec_resumes_run(
    client: httpx.AsyncClient, clerk: FakeClerk, session: AsyncSession, redis: Redis
) -> None:
    headers, _ = await _user(client, clerk)
    rid = (await _create(client, headers))["run"]["id"]
    url = f"/v1/runs/{rid}/approvals/spec"

    early = await client.post(url, json={"decision": "approve"}, headers=headers)
    assert early.status_code == 409

    await _await_approval(session, rid)
    h = {**headers, "Idempotency-Key": "approve-1"}
    ok = await client.post(url, json={"decision": "approve", "notes": "looks good"}, headers=h)
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "approved" and ok.json()["notes"] == "looks good"
    replay = await client.post(url, json={"decision": "approve", "notes": "looks good"}, headers=h)
    assert replay.json() == ok.json() and replay.headers["Idempotent-Replayed"] == "true"
    again = await client.post(url, json={"decision": "approve"}, headers=headers)
    assert again.status_code == 409
    assert await redis.zcard(RUN_QUEUE) == 2  # start + approval


async def test_viewer_cannot_approve_and_order_gate_is_not_open(
    client: httpx.AsyncClient, clerk: FakeClerk, session: AsyncSession
) -> None:
    headers, me = await _user(client, clerk)
    viewer_headers, viewer = await _user(client, clerk)
    rid = (await _create(client, headers))["run"]["id"]
    await _await_approval(session, rid)
    session.add(
        Membership(
            user_id=uuid.UUID(viewer["id"]),
            org_id=uuid.UUID(me["memberships"][0]["org_id"]),
            role="viewer",
        )
    )
    await session.commit()
    assert (await client.get(f"/v1/runs/{rid}", headers=viewer_headers)).status_code == 200
    denied = await client.post(
        f"/v1/runs/{rid}/approvals/spec", json={"decision": "approve"}, headers=viewer_headers
    )
    assert denied.status_code == 404
    order = await client.post(
        f"/v1/runs/{rid}/approvals/order", json={"decision": "approve"}, headers=headers
    )
    assert order.status_code == 404


def _parse_sse(text: str) -> list[dict[str, str]]:
    frames = []
    for block in text.replace("\r\n", "\n").split("\n\n"):
        fields = {}
        for line in block.splitlines():
            if line and not line.startswith(":") and ":" in line:
                k, _, v = line.partition(":")
                fields[k] = v.strip()
        if "data" in fields:
            frames.append(fields)
    return frames


async def test_sse_replays_after_last_event_id_and_closes_on_terminal(
    client: httpx.AsyncClient, clerk: FakeClerk, session: AsyncSession
) -> None:
    headers, _ = await _user(client, clerk)
    rid = uuid.UUID((await _create(client, headers))["run"]["id"])
    for seq, kind in enumerate(["run_started", "node_started", "node_finished", "run_finished"], 1):
        session.add(RunEventRow(run_id=rid, seq=seq, type=kind, payload={"n": seq}))
    await session.commit()

    resp = await client.get(f"/v1/runs/{rid}/events", headers={**headers, "Last-Event-ID": "2"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    frames = _parse_sse(resp.text)
    assert [f["id"] for f in frames] == ["3", "4"]
    assert [f["event"] for f in frames] == ["node_finished", "run_finished"]
    assert json.loads(frames[-1]["data"])["payload"] == {"n": 4}


async def test_event_stream_tails_redis_and_backfills_gaps(
    sessionmaker: async_sessionmaker[AsyncSession],
    redis: Redis,
    session: AsyncSession,
    client: httpx.AsyncClient,
    clerk: FakeClerk,
) -> None:
    headers, _ = await _user(client, clerk)
    rid = uuid.UUID((await _create(client, headers))["run"]["id"])
    session.add(RunEventRow(run_id=rid, seq=1, type="run_started", payload={}))
    await session.commit()

    async def never() -> bool:
        return False

    got: list[int] = []

    async def consume() -> None:
        async for event in run_events(sessionmaker, redis, rid, 0, never, block_ms=200):
            got.append(event["seq"])

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.3)
    assert got == [1]

    async def publish(seq: int, kind: str, to_redis: bool = True) -> None:
        session.add(RunEventRow(run_id=rid, seq=seq, type=kind, payload={}))
        await session.commit()
        if to_redis:
            event = {"run_id": str(rid), "seq": seq, "type": kind, "node": None, "payload": {}}
            await redis.xadd(stream_key(rid), {"event": json.dumps(event)}, id=stream_id(seq))

    await publish(2, "node_started")
    await publish(3, "node_finished", to_redis=False)  # lost publish: backfilled from Postgres
    await publish(4, "run_finished")
    await asyncio.wait_for(task, timeout=5)
    assert got == [1, 2, 3, 4]
