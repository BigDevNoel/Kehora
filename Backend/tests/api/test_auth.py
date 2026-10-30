import time

import httpx
import pytest

from tests.api.fake_clerk import FakeClerk

pytestmark = pytest.mark.db


async def test_healthz_is_public(client: httpx.AsyncClient) -> None:
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.headers["X-Request-ID"]


async def test_missing_token_is_401(client: httpx.AsyncClient) -> None:
    resp = await client.get("/v1/me")
    assert resp.status_code == 401
    assert resp.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 120},
        {"iss": "https://evil.example"},
        {"azp": "https://evil.example"},
        {"nbf": int(time.time()) + 600},
    ],
    ids=["expired", "wrong-issuer", "wrong-azp", "not-yet-valid"],
)
async def test_invalid_claims_are_401(
    client: httpx.AsyncClient, clerk: FakeClerk, overrides: dict[str, int | str]
) -> None:
    user = clerk.add_user("a@example.com")
    token = clerk.token(user["id"], **overrides)
    resp = await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_token_signed_by_other_key_is_401(
    client: httpx.AsyncClient, clerk: FakeClerk
) -> None:
    user = clerk.add_user("a@example.com")
    token = clerk.foreign_token(user["id"])
    resp = await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


async def test_first_request_provisions_user_with_personal_org(
    client: httpx.AsyncClient, clerk: FakeClerk
) -> None:
    user = clerk.add_user("ada@example.com")
    resp = await client.get("/v1/me", headers=clerk.headers(user["id"]))
    assert resp.status_code == 200, resp.text
    me = resp.json()
    assert me["email"] == "ada@example.com"
    assert me["name"] == "Ada Maker"
    assert me["role"] == "user"
    assert [(m["org_type"], m["role"]) for m in me["memberships"]] == [("personal", "owner")]

    again = await client.get("/v1/me", headers=clerk.headers(user["id"]))
    assert again.json()["id"] == me["id"]
    assert clerk.user_requests == 1


async def test_key_rotation_refetches_jwks(client: httpx.AsyncClient, clerk: FakeClerk) -> None:
    user = clerk.add_user("rot@example.com")
    assert (await client.get("/v1/me", headers=clerk.headers(user["id"]))).status_code == 200
    clerk.rotate()
    # The refetch is rate limited; pretend the last fetch was long ago.
    app_state = client._transport.app.state.kehora  # type: ignore[attr-defined]
    app_state.verifier.jwks._fetched_at = 0.0
    assert (await client.get("/v1/me", headers=clerk.headers(user["id"]))).status_code == 200
    assert clerk.jwks_requests == 2
