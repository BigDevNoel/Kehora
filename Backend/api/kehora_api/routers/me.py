import uuid

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from kehora_api.deps import Auth, Session
from kehora_db.models import Membership, Organization

router = APIRouter(tags=["me"])


class MembershipOut(BaseModel):
    org_id: uuid.UUID
    org_name: str
    org_type: str
    role: str


class MeOut(BaseModel):
    id: uuid.UUID
    email: str | None
    name: str | None
    role: str
    memberships: list[MembershipOut]


@router.get("/me")
async def get_me(auth: Auth, session: Session) -> MeOut:
    rows = await session.execute(
        select(Organization, Membership.role)
        .join(Membership, Membership.org_id == Organization.id)
        .where(Membership.user_id == auth.user.id)
        .order_by(Organization.created_at)
    )
    return MeOut(
        id=auth.user.id,
        email=auth.user.email,
        name=auth.user.name,
        role=auth.user.role,
        memberships=[
            MembershipOut(org_id=org.id, org_name=org.name, org_type=org.type, role=role)
            for org, role in rows
        ],
    )
