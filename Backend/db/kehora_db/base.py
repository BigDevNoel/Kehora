import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from kehora_common.clock import utcnow
from kehora_common.ids import new_id

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


class Entity(Base):
    """id (UUID v7) + created_at/updated_at (UTC) on every table (CLAUDE.md rule 7)."""

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, server_default=func.now(), onupdate=utcnow
    )


def enum_check(column: str, enum: type[StrEnum]) -> CheckConstraint:
    """Text column restricted to the enum's values (ADR-0005: no native PG enums)."""
    values = ", ".join(f"'{e.value}'" for e in enum)
    return CheckConstraint(f"{column} IN ({values})", name=column)
