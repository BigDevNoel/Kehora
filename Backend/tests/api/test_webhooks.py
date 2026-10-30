from typing import Any

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from kehora_db.models import AuditLog, Membership, Organization, User
from tests.api.fake_clerk import FakeClerk

pytestmark = pytest.mark.db


async def _send(
    client: httpx.AsyncClient, clerk: FakeClerk, kind: str, data: dict[str, Any]
) -> int:
    body, headers = clerk.webhook(kind, data)
    resp = await client.post("/v1/webhooks/clerk", content=body, headers=headers)
    return resp.status_code


async def _user(session: AsyncSession, clerk_id: str) -> User | None:
    return await session.scalar(select(User).where(User.clerk_id == clerk_id))


async def test_bad_signature_is_rejected_and_nothing_written(
    client: httpx.AsyncClient, clerk: FakeClerk, session: AsyncSession
) -> None:
    data = clerk.add_user("x@example.com")
    body, headers = clerk.webhook("user.created", data)
    headers["svix-signature"] = "v1,AAAA"
    resp = await client.post("/v1/webhooks/clerk", content=body, headers=headers)
    assert resp.status_code == 400
    assert await _user(session, data["id"]) is None


async def test_user_created_is_idempotent_and_makes_one_personal_org(
    client: httpx.AsyncClient, clerk: FakeClerk, session: AsyncSession
) -> None:
    data = clerk.add_user("w@example.com")
    assert await _send(client, clerk, "user.created", data) == 204
    assert await _send(client, clerk, "user.created", data) == 204  # Svix retry
    user = await _user(session, data["id"])
    assert user is not None and user.email == "w@example.com"
    orgs = await session.scalar(
        select(func.count()).select_from(Membership).where(Membership.user_id == user.id)
    )
    assert orgs == 1


async def test_role_change_from_public_metadata_is_audited(
    client: httpx.AsyncClient, clerk: FakeClerk, session: AsyncSession
) -> None:
    data = clerk.add_user("boss@example.com")
    await _send(client, clerk, "user.created", data)
    data["public_metadata"] = {"role": "admin"}
    assert await _send(client, clerk, "user.updated", data) == 204
    user = await _user(session, data["id"])
    assert user is not None and user.role == "admin"
    entry = await session.scalar(select(AuditLog).where(AuditLog.target == f"user:{user.id}"))
    assert entry is not None and entry.action == "user.role_changed"
    assert entry.metadata_ == {"from": "user", "to": "admin", "source": "clerk"}


async def test_unknown_role_in_metadata_falls_back_to_user(
    client: httpx.AsyncClient, clerk: FakeClerk, session: AsyncSession
) -> None:
    data = clerk.add_user("sneaky@example.com", role="god")
    await _send(client, clerk, "user.created", data)
    user = await _user(session, data["id"])
    assert user is not None and user.role == "user"


async def test_org_membership_lifecycle(
    client: httpx.AsyncClient, clerk: FakeClerk, session: AsyncSession
) -> None:
    data = clerk.add_user("team@example.com")
    org = {"id": "org_abc123", "name": "Acme Robotics"}
    membership = {
        "id": "orgmem_1",
        "role": "org:admin",
        "organization": org,
        "public_user_data": {"user_id": data["id"], "identifier": "team@example.com"},
    }
    # Membership may arrive before user.created.
    assert await _send(client, clerk, "organizationMembership.created", membership) == 204
    row = await session.scalar(select(Organization).where(Organization.clerk_org_id == org["id"]))
    assert row is not None and row.type == "business" and row.name == "Acme Robotics"
    user = await _user(session, data["id"])
    assert user is not None
    role = await session.scalar(
        select(Membership.role).where(Membership.org_id == row.id, Membership.user_id == user.id)
    )
    assert role == "admin"

    assert await _send(client, clerk, "organizationMembership.deleted", membership) == 204
    org_id, user_id = row.id, user.id
    session.expire_all()
    gone = await session.scalar(
        select(Membership).where(Membership.org_id == org_id, Membership.user_id == user_id)
    )
    assert gone is None


async def test_deleted_user_cannot_authenticate(
    client: httpx.AsyncClient, clerk: FakeClerk
) -> None:
    data = clerk.add_user("bye@example.com")
    assert (await client.get("/v1/me", headers=clerk.headers(data["id"]))).status_code == 200
    assert await _send(client, clerk, "user.deleted", {"id": data["id"], "deleted": True}) == 204
    assert (await client.get("/v1/me", headers=clerk.headers(data["id"]))).status_code == 401


async def test_unhandled_event_type_is_acknowledged(
    client: httpx.AsyncClient, clerk: FakeClerk
) -> None:
    assert await _send(client, clerk, "session.created", {"id": "sess_1"}) == 204
