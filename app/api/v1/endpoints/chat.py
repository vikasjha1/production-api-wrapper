import httpx
from fastapi import APIRouter, Depends, Response
from redis.asyncio import Redis

from app.api.deps import AuthenticatedClient, get_http_client, get_rate_limited_client, get_redis
from app.core.config import Settings, get_settings
from app.models.chat import ChatRequest, ChatResponse
from app.services.cache import get_cached_response, set_cached_response
from app.services.providers.registry import get_provider

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
    chat_response = await provider_instance.send_message(request)

    await set_cached_response(redis, provider, request, chat_response, settings.cache_ttl_seconds)
    response.headers["X-Cache"] = "MISS"

    return chat_response
