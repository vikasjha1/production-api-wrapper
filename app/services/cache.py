import hashlib
import json

from redis.asyncio import Redis

from app.models.chat import ChatRequest, ChatResponse


def _build_cache_key(provider: str, request: ChatRequest) -> str:
    payload = {
        "provider": provider,
        "model": request.model,
        "messages": [message.model_dump() for message in request.messages],
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
    }
    serialized = json.dumps(payload, sort_keys=True)
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    return f"cache:{provider}:{digest}"


async def get_cached_response(
    redis: Redis, provider: str, request: ChatRequest
) -> ChatResponse | None:
    key = _build_cache_key(provider, request)
    cached = await redis.get(key)
    if cached is None:
        return None
    return ChatResponse.model_validate_json(cached)


async def set_cached_response(
    redis: Redis,
    provider: str,
    request: ChatRequest,
    response: ChatResponse,
    ttl_seconds: int,
) -> None:
    key = _build_cache_key(provider, request)
    await redis.set(key, response.model_dump_json(), ex=ttl_seconds)
