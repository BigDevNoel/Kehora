"""Time helpers. CLAUDE.md rule 7: UTC everywhere."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    return datetime.now(UTC)
