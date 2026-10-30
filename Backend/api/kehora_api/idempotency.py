"""Idempotency-Key support for mutating endpoints (PRD 10, ADR-0005).

Flow per (user, key):
- first request: a placeholder row is committed in its own transaction, the handler runs,
  and `complete()` stores the response in the handler's transaction;
- same key + same body after completion: the stored response is replayed;
- same key + different body: 422; same key while the first is still running: 409;
- if the handler raises, the placeholder is removed so the client can retry.
"""

import hashlib
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from kehora_api.deps import Auth, State
from kehora_common.clock import utcnow
from kehora_common.ids import new_id
from kehora_db.models import IdempotencyKey

TTL = timedelta(hours=24)
HEADER = "Idempotency-Key"


class Idempotency:
    def __init__(self, state: State, auth: Auth, request: Request, body: bytes) -> None:
        self._state = state
        self._user_id = auth.user.id
        self.key = request.headers.get(HEADER)
        self._method = request.method
        self._path = request.url.path
        self._hash = hashlib.sha256(body).hexdigest()
        self._owned = False

    async def replay(self) -> JSONResponse | None:
        """Claim the key, or return the stored response for a completed duplicate."""
        if not self.key:
            return None
        if len(self.key) > 255:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Idempotency-Key too long")
        async with self._state.sessionmaker() as s:
            await s.execute(
                delete(IdempotencyKey).where(
                    IdempotencyKey.user_id == self._user_id,
                    IdempotencyKey.key == self.key,
                    IdempotencyKey.expires_at < utcnow(),
                )
            )
            inserted = await s.scalar(
                insert(IdempotencyKey)
                .values(
                    id=new_id(),
                    user_id=self._user_id,
                    key=self.key,
                    method=self._method,
                    path=self._path,
                    request_hash=self._hash,
                    expires_at=utcnow() + TTL,
                )
                .on_conflict_do_nothing(index_elements=["user_id", "key"])
                .returning(IdempotencyKey.id)
            )
            await s.commit()
            if inserted is not None:
                self._owned = True
                return None
            existing = await s.scalar(
                select(IdempotencyKey).where(
                    IdempotencyKey.user_id == self._user_id, IdempotencyKey.key == self.key
                )
            )
        assert existing is not None
        if (
            existing.request_hash != self._hash
            or existing.path != self._path
            or existing.method != self._method
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Idempotency-Key was already used with a different request",
            )
        if existing.response_status is None:
            raise HTTPException(status.HTTP_409_CONFLICT, "request with this key is in progress")
        return JSONResponse(
            existing.response_body,
            status_code=existing.response_status,
            headers={"Idempotent-Replayed": "true"},
        )

    async def complete(self, session: AsyncSession, status_code: int, body: Any) -> None:
        """Record the response in the caller's transaction (commit it with the work)."""
        if not self._owned:
            return
        row = await session.scalar(
            select(IdempotencyKey).where(
                IdempotencyKey.user_id == self._user_id, IdempotencyKey.key == self.key
            )
        )
        if row is not None:
            row.response_status = status_code
            row.response_body = jsonable_encoder(body)

    async def release(self) -> None:
        if not self._owned:
            return
        async with self._state.sessionmaker() as s:
            await s.execute(
                delete(IdempotencyKey).where(
                    IdempotencyKey.user_id == self._user_id,
                    IdempotencyKey.key == self.key,
                    IdempotencyKey.response_status.is_(None),
                )
            )
            await s.commit()


async def idempotency(state: State, auth: Auth, request: Request) -> AsyncIterator[Idempotency]:
    idem = Idempotency(state, auth, request, await request.body())
    try:
        yield idem
    except BaseException:
        await idem.release()
        raise


Idem = Annotated[Idempotency, Depends(idempotency)]
