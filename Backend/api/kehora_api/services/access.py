"""Org-level authorization (PRD 8.12 roles: owner, admin, member, viewer)."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from kehora_db.enums import MemberRole, OrgType
from kehora_db.models import Membership, Organization, User

RANK = {MemberRole.VIEWER: 0, MemberRole.MEMBER: 1, MemberRole.ADMIN: 2, MemberRole.OWNER: 3}


async def require_org_role(
    session: AsyncSession, user: User, org_id: uuid.UUID, minimum: MemberRole
) -> Membership:
    """Return the membership or raise 404 (not 403, so org ids are not probeable)."""
    membership = await session.scalar(
        select(Membership).where(Membership.user_id == user.id, Membership.org_id == org_id)
    )
    if membership is None or RANK[MemberRole(membership.role)] < RANK[minimum]:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    return membership


async def personal_org_id(session: AsyncSession, user: User) -> uuid.UUID:
    org_id = await session.scalar(
        select(Organization.id)
        .join(Membership, Membership.org_id == Organization.id)
        .where(Membership.user_id == user.id, Organization.type == OrgType.PERSONAL)
        .order_by(Organization.created_at)
        .limit(1)
    )
    if org_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "user has no personal organization")
    return org_id


async def member_org_ids(session: AsyncSession, user: User) -> list[uuid.UUID]:
    rows = await session.scalars(select(Membership.org_id).where(Membership.user_id == user.id))
    return list(rows)
