"""Cursor pagination (PRD 10). UUID v7 ids are time-ordered, so the last id is the cursor."""

import uuid

from fastapi import HTTPException, Query, status
from pydantic import BaseModel

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None


class PageParams(BaseModel):
    cursor: uuid.UUID | None
    limit: int


def page_params(
    cursor: str | None = Query(default=None, description="next_cursor from the previous page"),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> PageParams:
    try:
        parsed = uuid.UUID(cursor) if cursor else None
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid cursor") from None
    return PageParams(cursor=parsed, limit=limit)


def next_cursor(ids: list[uuid.UUID], limit: int) -> str | None:
    """Callers fetch limit + 1 rows; a cursor exists only if the extra row came back."""
    return str(ids[limit - 1]) if len(ids) > limit else None
