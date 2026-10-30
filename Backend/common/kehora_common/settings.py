"""Process configuration, read from the environment (and `.env` in local dev).

Every key here has a commented entry in the root `.env.example`. Secrets default to None so
that unit tests run without them; code that needs a secret calls `require()`.
"""

from enum import StrEnum
from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEV = "dev"
    TEST = "test"
    STAGING = "staging"
    PROD = "prod"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    env: Environment = Environment.DEV
    log_level: str = "INFO"
    log_format: str = Field(default="json", pattern="^(json|console)$")

    database_url: str = "postgresql+psycopg://kehora:kehora@localhost:5432/kehora"
    redis_url: str = "redis://localhost:6379/0"

    s3_endpoint_url: str | None = None
    s3_public_endpoint_url: str | None = None
    s3_region: str = "eu-west-1"
    s3_bucket: str = "kehora-dev"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None

    clerk_issuer: str | None = None
    clerk_secret_key: SecretStr | None = None
    clerk_webhook_signing_secret: SecretStr | None = None
    clerk_authorized_parties: list[str] = Field(default_factory=list)

    anthropic_api_key: SecretStr | None = None
    openai_api_key: SecretStr | None = None
    llm_routing_profile: str = "default"

    sandbox_provider: str = Field(default="local_docker", pattern="^(local_docker|e2b)$")
    sandbox_egress_proxy: str | None = None
    e2b_api_key: SecretStr | None = None

    sentry_dsn: str | None = None
    langsmith_api_key: SecretStr | None = None
    langsmith_project: str = "kehora-dev"

    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://localhost:5174"]
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def require[T](value: T | None, name: str) -> T:
    """Return a configured value or fail loudly naming the missing env var."""
    if value is None:
        raise RuntimeError(f"{name} is not set; see .env.example")
    return value
