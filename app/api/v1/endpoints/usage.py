from fastapi import APIRouter, Depends
from redis.asyncio import Redis

from app.api.deps import AuthenticatedClient, get_current_client, get_redis

router = APIRouter()


@router.get("/usage")
async def get_usage(
    client: AuthenticatedClient = Depends(get_current_client),
    redis: Redis = Depends(get_redis),
) -> dict[str, float | str]:
    raw_cost = await redis.get(f"cost:{client.client_id}")
    total_cost_usd = float(raw_cost) if raw_cost else 0.0

    return {"client_id": client.client_id, "total_cost_usd": round(total_cost_usd, 6)}
