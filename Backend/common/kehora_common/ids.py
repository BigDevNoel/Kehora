"""Primary key generation. CLAUDE.md rule 7: UUID v7 everywhere."""

import uuid

import uuid_utils


def new_id() -> uuid.UUID:
    """Return a time-ordered UUID v7 as a stdlib UUID."""
    return uuid.UUID(bytes=uuid_utils.uuid7().bytes)
