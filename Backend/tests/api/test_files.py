import uuid
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from kehora_db.models import AgentRun, Artifact, Project, ProjectVersion
from tests.api.fake_clerk import FakeClerk

pytestmark = [pytest.mark.db, pytest.mark.s3]

UPLOAD = {"filename": "broken part.jpg", "content_type": "image/jpeg", "size": 1024}


async def _signed_in(
    client: httpx.AsyncClient, clerk: FakeClerk
) -> tuple[dict[str, str], dict[str, Any]]:
    user = clerk.add_user(f"{uuid.uuid4().hex[:8]}@example.com")
    headers = clerk.headers(user["id"])
    me = (await client.get("/v1/me", headers=headers)).json()
    return headers, me


async def test_upload_returns_signed_put_under_personal_org(
    client: httpx.AsyncClient, clerk: FakeClerk
) -> None:
    headers, me = await _signed_in(client, clerk)
    resp = await client.post("/v1/uploads", json=UPLOAD, headers=headers)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    org_id = me["memberships"][0]["org_id"]
    assert body["key"].startswith(f"uploads/{org_id}/")
    assert body["key"].endswith("/broken_part.jpg")
    assert body["expires_in"] == 600
    assert "X-Amz-Signature" in body["url"]


@pytest.mark.parametrize(
    "patch,code",
    [({"content_type": "application/x-msdownload"}, 415), ({"size": 10**9}, 422)],
)
async def test_upload_rejects_bad_type_and_size(
    client: httpx.AsyncClient, clerk: FakeClerk, patch: dict[str, object], code: int
) -> None:
    headers, _ = await _signed_in(client, clerk)
    resp = await client.post("/v1/uploads", json={**UPLOAD, **patch}, headers=headers)
    assert resp.status_code == code


async def test_upload_into_foreign_org_is_404(client: httpx.AsyncClient, clerk: FakeClerk) -> None:
    headers, _ = await _signed_in(client, clerk)
    _, other = await _signed_in(client, clerk)
    foreign = other["memberships"][0]["org_id"]
    resp = await client.post("/v1/uploads", json={**UPLOAD, "org_id": foreign}, headers=headers)
    assert resp.status_code == 404


async def test_idempotency_key_replays_and_rejects_reuse(
    client: httpx.AsyncClient, clerk: FakeClerk
) -> None:
    headers, _ = await _signed_in(client, clerk)
    h = {**headers, "Idempotency-Key": "k-1"}
    first = await client.post("/v1/uploads", json=UPLOAD, headers=h)
    second = await client.post("/v1/uploads", json=UPLOAD, headers=h)
    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert second.headers.get("Idempotent-Replayed") == "true"

    other = await client.post("/v1/uploads", json={**UPLOAD, "size": 2048}, headers=h)
    assert other.status_code == 422


async def test_failed_request_releases_idempotency_key(
    client: httpx.AsyncClient, clerk: FakeClerk
) -> None:
    headers, _ = await _signed_in(client, clerk)
    h = {**headers, "Idempotency-Key": "k-retry"}
    bad = {**UPLOAD, "content_type": "application/x-msdownload"}
    assert (await client.post("/v1/uploads", json=bad, headers=h)).status_code == 415
    assert (await client.post("/v1/uploads", json=bad, headers=h)).status_code == 415


async def _artifact_for(session: AsyncSession, me: dict[str, Any]) -> Artifact:
    org_id = uuid.UUID(me["memberships"][0]["org_id"])
    user_id = uuid.UUID(me["id"])
    project = Project(org_id=org_id, owner_id=user_id, title="Stand")
    session.add(project)
    await session.flush()
    run = AgentRun(project_id=project.id, org_id=org_id, created_by_id=user_id, trigger_prompt="x")
    session.add(run)
    await session.flush()
    version = ProjectVersion(project_id=project.id, number=1, spec={}, created_by_run_id=run.id)
    session.add(version)
    await session.flush()
    artifact = Artifact(
        version_id=version.id, type="log", format="txt", s3_key="t/a.txt", sha256="0" * 64, size=1
    )
    session.add(artifact)
    await session.commit()
    return artifact


async def test_artifact_download_is_signed_and_member_only(
    client: httpx.AsyncClient, clerk: FakeClerk, session: AsyncSession
) -> None:
    headers, me = await _signed_in(client, clerk)
    other_headers, _ = await _signed_in(client, clerk)
    artifact = await _artifact_for(session, me)

    ok = await client.get(f"/v1/artifacts/{artifact.id}/download", headers=headers)
    assert ok.status_code == 200
    assert ok.json()["expires_in"] == 600 and "X-Amz-Signature" in ok.json()["url"]

    denied = await client.get(f"/v1/artifacts/{artifact.id}/download", headers=other_headers)
    assert denied.status_code == 404
    missing = await client.get(f"/v1/artifacts/{uuid.uuid4()}/download", headers=headers)
    assert missing.status_code == 404
