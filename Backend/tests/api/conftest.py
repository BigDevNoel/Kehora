from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from redis.asyncio import Redis

from kehora_api.main import create_app
from kehora_common.settings import Environment, Settings, get_settings
from tests.api.fake_clerk import API_URL, AZP, ISSUER, WEBHOOK_SECRET, FakeClerk
from tests.db_fixtures import *  # noqa: F403


@pytest.fixture
def clerk() -> FakeClerk:
    return FakeClerk()


@pytest.fixture
def settings(database_url: str) -> Settings:
    return get_settings().model_copy(
        update={
            "env": Environment.TEST,
            "database_url": database_url,
            "s3_bucket": "kehora-test",
            "redis_url": "redis://localhost:6379/14",
            "clerk_issuer": ISSUER,
            "clerk_api_url": API_URL,
            "clerk_secret_key": SecretStr("sk_test_fake"),
            "clerk_webhook_signing_secret": SecretStr(WEBHOOK_SECRET),
            "clerk_authorized_parties": [AZP],
            "sentry_dsn": None,
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
async def app(settings: Settings, clerk: FakeClerk, redis: Redis) -> AsyncIterator[FastAPI]:
    application = create_app(settings, http=clerk.client())
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://api.test") as c:
        yield c
