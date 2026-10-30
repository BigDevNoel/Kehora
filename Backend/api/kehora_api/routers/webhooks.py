"""POST /v1/webhooks/{provider}. Phase 0: Clerk only. Every webhook is signature-verified
(CLAUDE.md rule 6) before its body is parsed."""

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select
from svix.webhooks import Webhook, WebhookVerificationError

from kehora_api.deps import Session, State
from kehora_api.services import identity
from kehora_common.logging import get_logger
from kehora_common.settings import require
from kehora_db.models import User

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
log = get_logger(__name__)


async def _membership_user(session: Session, data: dict[str, Any]) -> User:
    public = data.get("public_user_data") or {}
    clerk_user_id = str(public["user_id"])
    user = await session.scalar(select(User).where(User.clerk_id == clerk_user_id))
    if user is not None:
        return user
    # Membership arrived before user.created; create the user from the public data. The
    # later user.created / user.updated event fills in the rest (including platform role).
    email = public.get("identifier")
    return await identity.upsert_user(
        session,
        {
            "id": clerk_user_id,
            "first_name": public.get("first_name"),
            "last_name": public.get("last_name"),
            "email_addresses": [{"id": "primary", "email_address": email}] if email else [],
            "primary_email_address_id": "primary",
        },
    )


@router.post("/clerk", status_code=status.HTTP_204_NO_CONTENT)
async def clerk_webhook(request: Request, state: State, session: Session) -> None:
    secret = require(
        state.settings.clerk_webhook_signing_secret, "CLERK_WEBHOOK_SIGNING_SECRET"
    ).get_secret_value()
    body = await request.body()
    headers = {
        k: request.headers.get(k, "") for k in ("svix-id", "svix-timestamp", "svix-signature")
    }
    try:
        Webhook(secret).verify(body, headers)
    except WebhookVerificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid signature") from exc

    event = json.loads(body)
    kind: str = event.get("type", "")
    data: dict[str, Any] = event.get("data") or {}
    match kind:
        case "user.created" | "user.updated":
            await identity.upsert_user(session, data)
        case "user.deleted":
            await identity.mark_user_deleted(session, str(data["id"]))
        case "organization.created" | "organization.updated":
            await identity.upsert_org(session, data)
        case "organization.deleted":
            await identity.delete_org(session, str(data["id"]))
        case "organizationMembership.created" | "organizationMembership.updated":
            user = await _membership_user(session, data)
            await identity.upsert_membership(session, data, user)
        case "organizationMembership.deleted":
            await identity.delete_membership(
                session,
                str(data["organization"]["id"]),
                str((data.get("public_user_data") or {})["user_id"]),
            )
        case _:
            log.info("clerk_webhook_ignored", type=kind)
            return
    await session.commit()
    log.info("clerk_webhook_applied", type=kind, svix_id=headers["svix-id"])
