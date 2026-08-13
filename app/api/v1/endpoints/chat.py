import httpx
from fastapi import APIRouter, Depends, Response
from redis.asyncio import Redis

from app.api.deps import AuthenticatedClient, get_http_client, get_rate_limited_client, get_redis
from app.core.config import Settings, get_settings
from app.models.chat import ChatRequest, ChatResponse
from app.services.cache import get_cached_response, set_cached_response
from app.services.cost_tracker import record_usage
from app.services.providers.registry import get_provider
from app.services.retry import with_retry

router = APIRouter()


@router.post("/chat/{provider}")
async def chat(
    provider: str,
    request: ChatRequest,
    response: Response,
    client: AuthenticatedClient = Depends(get_rate_limited_client),
    settings: Settings = Depends(get_settings),
    http_client: httpx.AsyncClient = Depends(get_http_client),
    redis: Redis = Depends(get_redis),
) -> ChatResponse:
    cached_response = await get_cached_response(redis, provider, request)
    if cached_response is not None:
        response.headers["X-Cache"] = "HIT"
        return cached_response

    provider_instance = get_provider(provider, settings, http_client)
    chat_response = await with_retry(
        lambda: provider_instance.send_message(request),
        max_attempts=settings.retry_max_attempts,
        base_delay=settings.retry_base_delay_seconds,
    )

    await set_cached_response(redis, provider, request, chat_response, settings.cache_ttl_seconds)
    await record_usage(redis, client.client_id, provider, chat_response)
    response.headers["X-Cache"] = "MISS"

    return chat_response
