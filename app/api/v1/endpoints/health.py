from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session, get_redis
from app.core.config import Settings, get_settings
from app.services.readiness import check_readiness

router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/ready")
async def readiness_check(
    redis: Redis = Depends(get_redis),
    db_session: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> JSONResponse:
    result = await check_readiness(redis, db_session, settings.readiness_check_timeout_seconds)

    body = {
        "status": "ready" if result.is_ready else "not_ready",
        "checks": {
            "redis": "ok" if result.redis_ok else "unreachable",
            "postgres": "ok" if result.postgres_ok else "unreachable",
        },
    }
    return JSONResponse(content=body, status_code=200 if result.is_ready else 503)
