"""Sync Clerk users, organizations and memberships into Postgres (ADR-0006).

Used by the Clerk webhook and by just-in-time provisioning on a user's first authenticated
request. Every write is an upsert keyed on the Clerk id, so webhook retries, out-of-order
delivery and the JIT/webhook race are all safe.
"""

from typing import Any

from sqlalchemy import delete, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kehora_common.clock import utcnow
from kehora_common.ids import new_id
from kehora_db.enums import MemberRole, OrgType, PlatformRole
from kehora_db.models import AuditLog, Membership, Organization, User

CLERK_ORG_ROLES = {
    "org:owner": MemberRole.OWNER,
    "org:admin": MemberRole.ADMIN,
    "org:member": MemberRole.MEMBER,
    "org:viewer": MemberRole.VIEWER,
}


def _primary_email(data: dict[str, Any]) -> str | None:
    primary = data.get("primary_email_address_id")
    emails = data.get("email_addresses") or []
    for e in emails:
        if e.get("id") == primary:
            return str(e.get("email_address"))
    return str(emails[0]["email_address"]) if emails else None


def _display_name(data: dict[str, Any]) -> str | None:
    parts = [data.get("first_name"), data.get("last_name")]
    name = " ".join(p for p in parts if p)
    return name or data.get("username") or None


def _platform_role(data: dict[str, Any]) -> PlatformRole:
    # Platform role is set only from Clerk's public_metadata, which only Clerk dashboard
    # admins and our backend can write; users cannot set it themselves.
    raw = (data.get("public_metadata") or {}).get("role")
    try:
        return PlatformRole(raw) if raw else PlatformRole.USER
    except ValueError:
        return PlatformRole.USER


async def upsert_user(session: AsyncSession, data: dict[str, Any]) -> User:
    """Create or update a user from a Clerk user object. New users get a personal org."""
    clerk_id = str(data["id"])
    previous_role = await session.scalar(select(User.role).where(User.clerk_id == clerk_id))
    role = _platform_role(data)
    values = {
        "clerk_id": clerk_id,
        "email": _primary_email(data),
        "name": _display_name(data),
        "role": role.value,
        "deleted_at": None,
    }
    stmt: Any = (
        insert(User)
        .values(id=new_id(), **values)
        .on_conflict_do_update(
            index_elements=[User.clerk_id],
            set_={**values, "updated_at": utcnow()},
        )
        .returning(User.id, literal_column("xmax = 0").label("inserted"))
    )
    row = (await session.execute(stmt)).one()
    user_id, inserted = row.id, row.inserted

    if inserted:
        org = Organization(name=values["name"] or "Personal", type=OrgType.PERSONAL)
        session.add(org)
        await session.flush()
        session.add(Membership(user_id=user_id, org_id=org.id, role=MemberRole.OWNER))
    elif previous_role is not None and previous_role != role.value:
        session.add(
            AuditLog(
                actor_id=None,
                action="user.role_changed",
                target=f"user:{user_id}",
                metadata_={"from": previous_role, "to": role.value, "source": "clerk"},
            )
        )
    await session.flush()
    user = await session.get(User, user_id, populate_existing=True)
    assert user is not None
    return user


async def mark_user_deleted(session: AsyncSession, clerk_id: str) -> None:
    user = await session.scalar(select(User).where(User.clerk_id == clerk_id))
    if user is not None and user.deleted_at is None:
        user.deleted_at = utcnow()
        await session.flush()


async def upsert_org(session: AsyncSession, data: dict[str, Any]) -> Organization:
    clerk_org_id = str(data["id"])
    values = {"clerk_org_id": clerk_org_id, "name": data.get("name") or "Organization"}
    stmt = (
        insert(Organization)
        .values(id=new_id(), type=OrgType.BUSINESS, **values)
        .on_conflict_do_update(
            index_elements=[Organization.clerk_org_id],
            set_={"name": values["name"], "updated_at": utcnow()},
        )
        .returning(Organization.id)
    )
    org_id = (await session.execute(stmt)).scalar_one()
    org = await session.get(Organization, org_id, populate_existing=True)
    assert org is not None
    return org


async def delete_org(session: AsyncSession, clerk_org_id: str) -> None:
    # Projects keep the org row as their owner; only memberships are removed so nobody
    # retains access. Data retention for deleted orgs is decided with GDPR/NDPA work.
    org_id = await session.scalar(
        select(Organization.id).where(Organization.clerk_org_id == clerk_org_id)
    )
    if org_id is not None:
        await session.execute(delete(Membership).where(Membership.org_id == org_id))


async def upsert_membership(session: AsyncSession, data: dict[str, Any], user: User) -> Membership:
    org = await upsert_org(session, data["organization"])
    role = CLERK_ORG_ROLES.get(str(data.get("role")), MemberRole.MEMBER)
    stmt = (
        insert(Membership)
        .values(id=new_id(), user_id=user.id, org_id=org.id, role=role)
        .on_conflict_do_update(
            index_elements=[Membership.user_id, Membership.org_id],
            set_={"role": role, "updated_at": utcnow()},
        )
        .returning(Membership.id)
    )
    membership_id = (await session.execute(stmt)).scalar_one()
    membership = await session.get(Membership, membership_id, populate_existing=True)
    assert membership is not None
    return membership


async def delete_membership(session: AsyncSession, clerk_org_id: str, clerk_user_id: str) -> None:
    org_id = await session.scalar(
        select(Organization.id).where(Organization.clerk_org_id == clerk_org_id)
    )
    user_id = await session.scalar(select(User.id).where(User.clerk_id == clerk_user_id))
    if org_id is not None and user_id is not None:
        await session.execute(
            delete(Membership).where(Membership.org_id == org_id, Membership.user_id == user_id)
        )
