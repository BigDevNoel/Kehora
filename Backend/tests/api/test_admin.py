import uuid

import httpx
import pytest

from tests.api.fake_clerk import FakeClerk

pytestmark = [pytest.mark.db, pytest.mark.redis]


async def _headers(client: httpx.AsyncClient, clerk: FakeClerk, role: str | None) -> dict[str, str]:
    data = clerk.add_user(f"{uuid.uuid4().hex[:8]}@example.com", role=role)
    headers = clerk.headers(data["id"])
    assert (await client.get("/v1/me", headers=headers)).status_code == 200
    return headers


@pytest.mark.parametrize("path", ["/v1/admin/users", "/v1/admin/projects", "/v1/admin/runs"])
async def test_admin_lists_are_staff_only(
    client: httpx.AsyncClient, clerk: FakeClerk, path: str
) -> None:
    assert (await client.get(path)).status_code == 401
    user = await _headers(client, clerk, None)
    assert (await client.get(path, headers=user)).status_code == 403
    for role in ("support", "admin"):
        staff = await _headers(client, clerk, role)
        resp = await client.get(path, headers=staff)
        assert resp.status_code == 200, resp.text
        assert "items" in resp.json()


async def test_admin_sees_everyones_projects_and_filters_runs(
    client: httpx.AsyncClient, clerk: FakeClerk
) -> None:
    maker = await _headers(client, clerk, None)
    created = (await client.post("/v1/projects", json={"prompt": "A lamp"}, headers=maker)).json()
    admin = await _headers(client, clerk, "admin")

    projects = (await client.get("/v1/admin/projects?limit=100", headers=admin)).json()
    assert created["project"]["id"] in [p["id"] for p in projects["items"]]
    queued = (await client.get("/v1/admin/runs?status=queued&limit=100", headers=admin)).json()
    assert created["run"]["id"] in [r["id"] for r in queued["items"]]
    done = (await client.get("/v1/admin/runs?status=succeeded&limit=100", headers=admin)).json()
    assert created["run"]["id"] not in [r["id"] for r in done["items"]]
