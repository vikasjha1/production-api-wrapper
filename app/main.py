from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging
from app.db.session import build_db_engine, build_session_factory
from app.middleware.metrics import MetricsMiddleware
from app.middleware.request_logging import RequestLoggingMiddleware
from app.services.http_client_factory import build_http_client
from app.services.metrics import build_metrics, build_metrics_registry


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()
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


def create_app() -> FastAPI:
    configure_logging()
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    register_exception_handlers(app)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(MetricsMiddleware)
    app.include_router(api_router, prefix="/v1")

    @app.get("/")
    def root() -> dict[str, str]:
        return {"message": f"{settings.app_name} is running"}

    @app.get("/metrics")
    def metrics() -> Response:
        return Response(generate_latest(app.state.metrics_registry), media_type=CONTENT_TYPE_LATEST)

    return app


app = create_app()
