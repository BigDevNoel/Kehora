"""Shared fixtures for tests that need the compose Postgres.

A throwaway `kehora_test` database is created once per session and migrated with Alembic, so
tests exercise the real migration (triggers, constraints), not `metadata.create_all`.
"""

from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from kehora_common.settings import get_settings
from kehora_db.session import make_engine, make_sessionmaker

DB_DIR = Path(__file__).resolve().parents[1] / "db"


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    base = make_url(get_settings().database_url)
    test_url = base.set(database="kehora_test")
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text("DROP DATABASE IF EXISTS kehora_test WITH (FORCE)"))
        conn.execute(text("CREATE DATABASE kehora_test"))
    url = test_url.render_as_string(hide_password=False)

    cfg = Config(str(DB_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(DB_DIR / "alembic"))
    get_settings.cache_clear()
    mp = pytest.MonkeyPatch()
    mp.setenv("DATABASE_URL", url)
    command.upgrade(cfg, "head")
    try:
        yield url
    finally:
        mp.undo()
        get_settings.cache_clear()
        admin.dispose()


@pytest.fixture(scope="session")
async def db_engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = make_engine(database_url)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="session")
def sessionmaker(db_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return make_sessionmaker(db_engine)


@pytest.fixture
async def session(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    async with sessionmaker() as s:
        yield s
        await s.rollback()
