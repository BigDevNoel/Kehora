"""FastAPI app factory. The API validates, stores, enqueues and streams; it never runs builds."""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import httpx
import sentry_sdk
import structlog
from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from kehora_api.auth.clerk import ClerkVerifier
from kehora_api.deps import AppState
from kehora_api.routers import files, me, projects, webhooks
from kehora_common.logging import configure_logging, get_logger
from kehora_common.settings import Environment, Settings, get_settings
from kehora_common.storage import Storage
from kehora_db.session import make_engine, make_sessionmaker

log = get_logger(__name__)


def create_app(settings: Settings | None = None, http: httpx.AsyncClient | None = None) -> FastAPI:
    """`http` is injectable so tests can mock Clerk (JWKS, Backend API)."""
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.env, send_default_pii=False)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = make_engine(settings.database_url)
        client = http or httpx.AsyncClient()
        storage = Storage(settings)
        if settings.env in (Environment.DEV, Environment.TEST):
            await run_in_threadpool(storage.ensure_bucket)
        verifier = (
            ClerkVerifier(settings.clerk_issuer, settings.clerk_authorized_parties, client)
            if settings.clerk_issuer
            else None
        )
        app.state.kehora = AppState(
            settings=settings,
            sessionmaker=make_sessionmaker(engine),
            http=client,
            storage=storage,
            verifier=verifier,
        )
        arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))
        app.state.kehora.extras.update(arq=arq, redis=arq)
        log.info("api_started", env=settings.env, auth=verifier is not None)
        try:
            yield
        finally:
            await arq.aclose()
            await client.aclose()
            await engine.dispose()

    app = FastAPI(title="Kehora API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["Idempotent-Replayed"],
    )

    @app.middleware("http")
    async def request_context(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    v1 = APIRouter(prefix="/v1")
    v1.include_router(me.router)
    v1.include_router(files.router)
    v1.include_router(projects.router)
    v1.include_router(webhooks.router)
    app.include_router(v1)
    return app
