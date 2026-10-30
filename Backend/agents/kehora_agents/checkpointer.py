"""LangGraph Postgres checkpointer in its own `langgraph` schema (ADR-0005), so Alembic and
the checkpointer never manage the same tables."""

import contextlib
from collections.abc import AsyncIterator

import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

SCHEMA = "langgraph"


def psycopg_dsn(sqlalchemy_url: str) -> str:
    """postgresql+psycopg://... -> postgresql://... (psycopg wants a libpq URL)."""
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


@contextlib.asynccontextmanager
async def open_checkpointer(database_url: str) -> AsyncIterator[AsyncPostgresSaver]:
    dsn = psycopg_dsn(database_url)
    async with await psycopg.AsyncConnection.connect(dsn, autocommit=True) as conn:
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")
    pool = AsyncConnectionPool(
        dsn,
        min_size=1,
        max_size=10,
        open=False,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
            "options": f"-c search_path={SCHEMA}",
        },
    )
    await pool.open()
    try:
        saver = AsyncPostgresSaver(pool)  # type: ignore[arg-type]
        await saver.setup()
        yield saver
    finally:
        await pool.close()
