import asyncio
from collections.abc import AsyncGenerator
from pathlib import Path

import httpx
import respx
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient
from prometheus_client import generate_latest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db_session, get_redis
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.main import app
from app.services.metrics import build_metrics, build_metrics_registry
from app.services.providers.anthropic import ANTHROPIC_API_URL
from app.services.providers.openai import OPENAI_API_URL


def test_metrics_records_requests_and_latency() -> None:
    registry = build_metrics_registry()
    metrics = build_metrics(registry)

    metrics.request_count.labels(method="GET", path="/v1/health", status_code=200).inc()
    metrics.request_latency.labels(method="GET", path="/v1/health").observe(0.05)

    output = generate_latest(registry).decode()

    assert 'gateway_requests_total{method="GET",path="/v1/health",status_code="200"} 1.0' in output
    assert "gateway_request_duration_seconds" in output


def test_metrics_endpoint_records_real_requests_by_route_template() -> None:
    with TestClient(app) as client:
        client.get("/v1/health")
        client.get("/v1/health")

        response = client.get("/metrics")

    assert response.status_code == 200
    body = response.text
    assert 'gateway_requests_total{method="GET",path="/v1/health",status_code="200"} 2.0' in body


@respx.mock
def test_metrics_collapse_different_providers_into_one_route_template(tmp_path: Path) -> None:
    respx.post(ANTHROPIC_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "hi"}],
                "model": "claude-haiku-4-5-20251001",
                "usage": {"input_tokens": 5, "output_tokens": 2},
            },
        )
    )
    respx.post(OPENAI_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2024-07-18",
                "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 2},
            },
        )
    )

    def override_settings() -> Settings:
        return Settings(
            api_keys={"test-key-abc": "test-client"},
            anthropic_api_key="fake-anthropic-key",
            openai_api_key="fake-openai-key",
        )

    db_path = tmp_path / "test.db"

    async def _create_schema() -> None:
        setup_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
        async with setup_engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await setup_engine.dispose()

    asyncio.run(_create_schema())

    test_engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)

    async def override_get_db_session() -> AsyncGenerator[AsyncSession]:
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_redis] = lambda: FakeRedis()
    app.dependency_overrides[get_db_session] = override_get_db_session

    headers = {"X-API-Key": "test-key-abc"}
    payload = {"model": "x", "messages": [{"role": "user", "content": "hi"}]}

    with TestClient(app) as client:
        client.post("/v1/chat/anthropic", headers=headers, json=payload)
        client.post("/v1/chat/openai", headers=headers, json=payload)
        response = client.get("/metrics")

    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_redis, None)
    app.dependency_overrides.pop(get_db_session, None)

    body = response.text
    # Both providers collapse into ONE labeled series, not two — proving
    # the cardinality-safety design actually works, not just in theory.
    assert 'path="/v1/chat/{provider}"' in body
    assert (
        'gateway_requests_total{method="POST",path="/v1/chat/{provider}",status_code="200"} 2.0'
        in body
    )
    assert 'path="/v1/chat/anthropic"' not in body
    assert 'path="/v1/chat/openai"' not in body
