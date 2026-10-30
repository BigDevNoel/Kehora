"""Enums owned by the database layer (ADR-0005).

Shapes shared with agents (ProjectKind, ArtifactType, CheckStatus, RunEventType) come from
kehora_schemas and are re-exported here, never redefined.
"""

from enum import StrEnum

from kehora_schemas import ArtifactType, CheckStatus, ProjectKind, RunEventType


class PlatformRole(StrEnum):
    USER = "user"
    SUPPORT = "support"
    ADMIN = "admin"


class OrgType(StrEnum):
    PERSONAL = "personal"
    BUSINESS = "business"
    SCHOOL = "school"
    MAKER = "maker"


class MemberRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


class Visibility(StrEnum):
    PRIVATE = "private"
    UNLISTED = "unlisted"
    PUBLIC = "public"


class RunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    FAILED = "failed"
    SUCCEEDED = "succeeded"
    CANCELLED = "cancelled"


class ApprovalGate(StrEnum):
    SPEC = "spec"
    ORDER = "order"


class ApprovalStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


__all__ = [
    "ApprovalGate",
    "ApprovalStatus",
    "ArtifactType",
    "CheckStatus",
    "MemberRole",
    "OrgType",
    "PlatformRole",
    "ProjectKind",
    "RunEventType",
    "RunStatus",
    "Visibility",
]
