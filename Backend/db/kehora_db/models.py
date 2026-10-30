"""Phase 0 tables (PRD 9, ADR-0005)."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from kehora_db.base import Entity, enum_check
from kehora_db.enums import (
    ApprovalGate,
    ApprovalStatus,
    ArtifactType,
    CheckStatus,
    MemberRole,
    OrgType,
    PlatformRole,
    ProjectKind,
    RunEventType,
    RunStatus,
    Visibility,
)

TZ = DateTime(timezone=True)


def _json() -> Any:
    return mapped_column(JSONB, nullable=False, default=dict, server_default="{}")


class User(Entity):
    __tablename__ = "users"
    __table_args__ = (enum_check("role", PlatformRole),)

    clerk_id: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    country: Mapped[str | None] = mapped_column(String(2))
    locale: Mapped[str | None] = mapped_column(String(35))
    role: Mapped[str] = mapped_column(
        String(16), default=PlatformRole.USER, server_default=PlatformRole.USER
    )
    deleted_at: Mapped[datetime | None] = mapped_column(TZ)


class Organization(Entity):
    __tablename__ = "organizations"
    __table_args__ = (enum_check("type", OrgType),)

    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(16))
    clerk_org_id: Mapped[str | None] = mapped_column(String(64), unique=True)


class Membership(Entity):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id"),
        enum_check("role", MemberRole),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))


class Project(Entity):
    __tablename__ = "projects"
    __table_args__ = (
        enum_check("kind", ProjectKind),
        enum_check("visibility", Visibility),
        Index("ix_projects_org_id_created_at", "org_id", "created_at"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str | None] = mapped_column(String(16))
    visibility: Mapped[str] = mapped_column(
        String(16), default=Visibility.PRIVATE, server_default=Visibility.PRIVATE
    )
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_versions.id", use_alter=True)
    )
    forked_from_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("projects.id"))


class ProjectVersion(Entity):
    """Immutable once created (DB trigger)."""

    __tablename__ = "project_versions"
    __table_args__ = (UniqueConstraint("project_id", "number"),)

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    number: Mapped[int] = mapped_column(Integer)
    spec: Mapped[dict[str, Any]] = _json()
    parent_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_versions.id"))
    created_by_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("agent_runs.id", use_alter=True)
    )


class Artifact(Entity):
    __tablename__ = "artifacts"
    __table_args__ = (enum_check("type", ArtifactType),)

    version_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project_versions.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(16))
    format: Mapped[str] = mapped_column(String(16))
    s3_key: Mapped[str] = mapped_column(String(1024))
    sha256: Mapped[str] = mapped_column(String(64))
    size: Mapped[int] = mapped_column(BigInteger)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )


class AgentRun(Entity):
    __tablename__ = "agent_runs"
    __table_args__ = (enum_check("status", RunStatus),)

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    created_by_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project_versions.id"))
    status: Mapped[str] = mapped_column(
        String(24), default=RunStatus.QUEUED, server_default=RunStatus.QUEUED, index=True
    )
    trigger_prompt: Mapped[str] = mapped_column(Text)
    model_usage: Mapped[dict[str, Any]] = _json()
    cost_minor: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    cost_currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(TZ)
    finished_at: Mapped[datetime | None] = mapped_column(TZ)


class RunEventRow(Entity):
    """Append-only (DB trigger). Replayed for the build log and SSE resume."""

    __tablename__ = "run_events"
    __table_args__ = (
        UniqueConstraint("run_id", "seq"),
        enum_check("type", RunEventType),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("agent_runs.id", ondelete="CASCADE"))
    seq: Mapped[int] = mapped_column(Integer)
    type: Mapped[str] = mapped_column(String(32))
    node: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = _json()


class Check(Entity):
    __tablename__ = "checks"
    __table_args__ = (enum_check("status", CheckStatus),)

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    artifact_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artifacts.id"))
    engine: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(8))
    report: Mapped[dict[str, Any]] = _json()


class Approval(Entity):
    __tablename__ = "approvals"
    __table_args__ = (
        enum_check("gate", ApprovalGate),
        enum_check("status", ApprovalStatus),
    )

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="CASCADE"), index=True
    )
    gate: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(
        String(16), default=ApprovalStatus.PENDING, server_default=ApprovalStatus.PENDING
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(TZ)
    notes: Mapped[str | None] = mapped_column(Text)


class CreditLedgerEntry(Entity):
    """Append-only (DB trigger). Integer credits, not money."""

    __tablename__ = "credit_ledger"

    org_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"), index=True)
    delta: Mapped[int] = mapped_column(BigInteger)
    reason: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("agent_runs.id"))
    balance_after: Mapped[int] = mapped_column(BigInteger)


class AuditLog(Entity):
    """Append-only (DB trigger). Admin and money actions."""

    __tablename__ = "audit_log"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64), index=True)
    target: Mapped[str] = mapped_column(String(128))
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}"
    )


class IdempotencyKey(Entity):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "key"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(255))
    method: Mapped[str] = mapped_column(String(8))
    path: Mapped[str] = mapped_column(String(512))
    request_hash: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[Any | None] = mapped_column(JSONB)
    expires_at: Mapped[datetime] = mapped_column(TZ, index=True)
