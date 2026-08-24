import asyncio

import pytest
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.services.readiness import check_readiness


async def _make_session_factory(db_path):  # type: ignore[no-untyped-def]
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.mark.asyncio
async def test_ready_when_both_dependencies_reachable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    redis = FakeRedis()
    session_factory = await _make_session_factory(tmp_path / "test.db")

    async with session_factory() as session:
        result = await check_readiness(redis, session, timeout_seconds=2.0)

    assert result.redis_ok is True
    assert result.postgres_ok is True
    assert result.is_ready is True


@pytest.mark.asyncio
async def test_not_ready_when_redis_unreachable(tmp_path) -> None:  # type: ignore[no-untyped-def]
    # A real client pointed at a port nothing is listening on, so ping()
    # genuinely fails with a real connection error — not a simulated one.
    redis = Redis.from_url("redis://localhost:1")

    session_factory = await _make_session_factory(tmp_path / "test.db")

    async with session_factory() as session:
        result = await check_readiness(redis, session, timeout_seconds=2.0)

    assert result.redis_ok is False
    assert result.postgres_ok is True
    assert result.is_ready is False


@pytest.mark.asyncio
async def test_check_times_out_instead_of_hanging_forever() -> None:
    async def _never_finishes() -> None:
        await asyncio.sleep(10)

    from app.services.readiness import _check_with_timeout

    result = await _check_with_timeout(_never_finishes(), timeout_seconds=0.05)

    assert result is False
