from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis

from app.api.v1.router import api_router
from app.core.config import Settings, get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import build_db_engine, build_session_factory
from app.middleware.metrics import MetricsMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware
from app.services.http_client_factory import build_http_client
from app.services.metrics import build_metrics, build_metrics_registry


def create_app(settings: Settings | None = None) -> FastAPI:
    configure_logging()
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        app.state.http_client = build_http_client(settings)
        app.state.redis = Redis.from_url(settings.redis_url)
        app.state.circuit_breakers = {}
        app.state.db_engine = build_db_engine(settings)
        app.state.db_session_factory = build_session_factory(app.state.db_engine)
        app.state.metrics_registry = build_metrics_registry()
        app.state.metrics = build_metrics(app.state.metrics_registry)
        yield
        await app.state.http_client.aclose()
        await app.state.redis.aclose()
        await app.state.db_engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    register_exception_handlers(app)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(MetricsMiddleware)
    if settings.cors_allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allowed_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["X-API-Key", "Content-Type", "Idempotency-Key"],
        )
    app.include_router(api_router, prefix="/v1")

    @app.get("/")
    def root() -> dict[str, str]:
        return {"message": f"{settings.app_name} is running"}

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(app.state.metrics_registry), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
