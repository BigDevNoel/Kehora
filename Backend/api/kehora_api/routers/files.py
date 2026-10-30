"""Signed upload and download URLs (PRD 10: POST /v1/uploads, GET /v1/artifacts/{id}/download).

Files never stream through the API; clients talk to S3 with short-lived signed URLs.
"""

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from kehora_api.deps import Auth, Session, State
from kehora_api.idempotency import Idem
from kehora_api.services.access import personal_org_id, require_org_role
from kehora_common.ids import new_id
from kehora_common.storage import SIGNED_URL_TTL_SECONDS
from kehora_db.enums import MemberRole
from kehora_db.models import Artifact, Project, ProjectVersion

router = APIRouter(tags=["files"])

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_UPLOAD_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "application/pdf",
    "audio/webm",
    "audio/mpeg",
    "audio/mp4",
}


class UploadRequest(BaseModel):
    filename: Annotated[str, Field(min_length=1, max_length=200)]
    content_type: str
    size: Annotated[int, Field(gt=0, le=MAX_UPLOAD_BYTES)]
    org_id: uuid.UUID | None = None


class SignedUrl(BaseModel):
    url: str
    key: str
    expires_in: int


def _safe_name(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._")
    return cleaned[:100] or "file"


@router.post("/uploads", status_code=status.HTTP_201_CREATED, response_model=SignedUrl)
async def create_upload(
    body: UploadRequest, auth: Auth, session: Session, state: State, idem: Idem
) -> SignedUrl | JSONResponse:
    if (replayed := await idem.replay()) is not None:
        return replayed
    if body.content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "content type not allowed")
    org_id = body.org_id or await personal_org_id(session, auth.user)
    await require_org_role(session, auth.user, org_id, MemberRole.MEMBER)
    key = f"uploads/{org_id}/{new_id()}/{_safe_name(body.filename)}"
    url = state.storage.presign_put(key, body.content_type)
    result = SignedUrl(url=url, key=key, expires_in=SIGNED_URL_TTL_SECONDS)
    await idem.complete(session, status.HTTP_201_CREATED, result)
    await session.commit()
    return result


@router.get("/artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: uuid.UUID, auth: Auth, session: Session, state: State
) -> SignedUrl:
    row = (
        await session.execute(
            select(Artifact, Project.org_id)
            .join(ProjectVersion, ProjectVersion.id == Artifact.version_id)
            .join(Project, Project.id == ProjectVersion.project_id)
            .where(Artifact.id == artifact_id)
        )
    ).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "not found")
    artifact, org_id = row
    await require_org_role(session, auth.user, org_id, MemberRole.VIEWER)
    url = state.storage.presign_get(artifact.s3_key)
    return SignedUrl(url=url, key=artifact.s3_key, expires_in=SIGNED_URL_TTL_SECONDS)
