import asyncio
from collections.abc import Awaitable
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ReadinessResult:
    redis_ok: bool
    postgres_ok: bool

    @property
    def is_ready(self) -> bool:
        return self.redis_ok and self.postgres_ok


async def check_readiness(
    redis: Redis, db_session: AsyncSession, timeout_seconds: float
) -> ReadinessResult:
    redis_ok = await _check_with_timeout(redis.ping(), timeout_seconds)
    postgres_ok = await _check_with_timeout(db_session.execute(text("SELECT 1")), timeout_seconds)
    return ReadinessResult(redis_ok=redis_ok, postgres_ok=postgres_ok)


async def _check_with_timeout(check: Awaitable[object], timeout_seconds: float) -> bool:
    try:
        await asyncio.wait_for(check, timeout=timeout_seconds)
        return True
    except Exception:
        return False
