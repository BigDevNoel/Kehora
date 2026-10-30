import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from kehora_agents.checkpointer import open_checkpointer
from kehora_agents.graph import build_graph
from kehora_agents.services import Services
from kehora_common.settings import Environment, Settings, get_settings
from kehora_common.storage import Storage
from kehora_db.models import AgentRun, Organization, Project, User
from kehora_engines_runner.local_docker import LocalDockerSandbox
from kehora_llm.gateway import build_gateway
from tests.db_fixtures import *  # noqa: F403


@pytest.fixture
def settings(database_url: str) -> Settings:
    return get_settings().model_copy(
        update={
            "env": Environment.TEST,
            "database_url": database_url,
            "redis_url": "redis://localhost:6379/15",
            "s3_bucket": "kehora-test",
            "llm_routing_profile": "test",
            "log_format": "console",
        }
    )


@pytest.fixture
async def redis(settings: Settings) -> AsyncIterator[Redis]:
    client = Redis.from_url(settings.redis_url)
    await client.flushdb()
    yield client
    await client.aclose()


@pytest.fixture
async def svc(
    settings: Settings, redis: Redis, sessionmaker: async_sessionmaker[AsyncSession]
) -> Services:
    storage = Storage(settings)
    storage.ensure_bucket()
    return Services(
        settings=settings,
        sessionmaker=sessionmaker,
        redis=redis,
        gateway=build_gateway(settings),
        sandbox=LocalDockerSandbox(),
        storage=storage,
    )


@pytest.fixture
async def graph(svc: Services, database_url: str) -> AsyncIterator[Any]:
    async with open_checkpointer(database_url) as saver:
        yield build_graph(svc, saver)


@pytest.fixture
async def run(svc: Services) -> AgentRun:
    async with svc.sessionmaker() as s, s.begin():
        user = User(clerk_id=f"user_{uuid.uuid4().hex}")
        org = Organization(name="Personal", type="personal")
        s.add_all([user, org])
        await s.flush()
        project = Project(org_id=org.id, owner_id=user.id, title="New project")
        s.add(project)
        await s.flush()
        agent_run = AgentRun(
            project_id=project.id,
            org_id=org.id,
            created_by_id=user.id,
            trigger_prompt="A desk stand for my phone",
        )
        s.add(agent_run)
    return agent_run
