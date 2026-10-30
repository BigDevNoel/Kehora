"""Request-scoped dependencies: settings, DB session, storage and the authenticated user."""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Annotated, Any

import httpx
import structlog
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kehora_api.auth.clerk import AuthError, ClerkClaims, ClerkVerifier
from kehora_api.services import clerk_api, identity
from kehora_common.logging import get_logger
from kehora_common.settings import Settings
from kehora_common.storage import Storage
from kehora_db.enums import PlatformRole
from kehora_db.models import User

log = get_logger(__name__)


@dataclass
class AppState:
    settings: Settings
    sessionmaker: async_sessionmaker[AsyncSession]
    http: httpx.AsyncClient
    storage: Storage
    verifier: ClerkVerifier | None
    extras: dict[str, Any] = field(default_factory=dict)


def app_state(request: Request) -> AppState:
    state: AppState = request.app.state.kehora
    return state


State = Annotated[AppState, Depends(app_state)]


async def db_session(state: State) -> AsyncIterator[AsyncSession]:
    async with state.sessionmaker() as session:
        yield session


Session = Annotated[AsyncSession, Depends(db_session)]


@dataclass(frozen=True)
class CurrentUser:
    user: User
    claims: ClerkClaims


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, detail=detail, headers={"WWW-Authenticate": "Bearer"}
    )


async def current_user(request: Request, state: State, session: Session) -> CurrentUser:
    if state.verifier is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "auth is not configured")
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("missing bearer token")
    try:
        claims = await state.verifier.verify(token)
    except AuthError as exc:
        raise _unauthorized(f"invalid token: {exc}") from exc

    user = await session.scalar(select(User).where(User.clerk_id == claims.user_id))
    if user is None:
        # First request before the user.created webhook arrived (or no webhook tunnel in
        # local dev): provision from the Clerk Backend API through the same upsert (ADR-0006).
        data = await clerk_api.fetch_user(state.http, state.settings, claims.user_id)
        user = await identity.upsert_user(session, data)
        await session.commit()
        log.info("user_provisioned_jit", user_id=str(user.id))
    if user.deleted_at is not None:
        raise _unauthorized("user is deleted")
    structlog.contextvars.bind_contextvars(user_id=str(user.id))
    return CurrentUser(user=user, claims=claims)


Auth = Annotated[CurrentUser, Depends(current_user)]


async def staff_user(auth: Auth) -> CurrentUser:
    if auth.user.role not in (PlatformRole.ADMIN, PlatformRole.SUPPORT):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "staff only")
    return auth


Staff = Annotated[CurrentUser, Depends(staff_user)]
