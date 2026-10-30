"""Run event stream conventions shared by the worker (writer) and the API (SSE reader).

Postgres `run_events` is the source of truth. Each event is also XADDed to the Redis stream
`run:{run_id}:events` with the explicit entry id `{seq}-0`, so a reader that has seen seq N can
XREAD from `N-0` and receive exactly the events after it (ADR-0009).
"""

import uuid

STREAM_MAXLEN = 10_000
TERMINAL_EVENTS = frozenset({"run_finished", "run_failed"})


def stream_key(run_id: uuid.UUID | str) -> str:
    return f"run:{run_id}:events"


def stream_id(seq: int) -> str:
    return f"{seq}-0"


def seq_from_stream_id(entry_id: bytes | str) -> int:
    raw = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
    return int(raw.split("-", 1)[0])
