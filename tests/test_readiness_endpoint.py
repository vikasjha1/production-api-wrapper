import asyncio
from collections.abc import AsyncGenerator, Generator
from pathlib import Path

import pytest
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.api.deps import get_db_session, get_redis
from app.db.base import Base
from app.main import app


@pytest.fixture
def ready_client(tmp_path: Path) -> Generator[TestClient, None, None]:
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

    app.dependency_overrides[get_redis] = lambda: FakeRedis()
    app.dependency_overrides[get_db_session] = override_get_db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_redis, None)
    app.dependency_overrides.pop(get_db_session, None)


def test_ready_returns_200_when_dependencies_are_reachable(ready_client: TestClient) -> None:
    response = ready_client.get("/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "checks": {"redis": "ok", "postgres": "ok"}}


def test_ready_returns_503_when_redis_is_unreachable(ready_client: TestClient) -> None:
    app.dependency_overrides[get_redis] = lambda: Redis.from_url("redis://localhost:1")

    response = ready_client.get("/v1/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["redis"] == "unreachable"
    assert body["checks"]["postgres"] == "ok"
