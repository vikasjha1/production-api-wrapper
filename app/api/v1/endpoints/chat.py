import httpx
from fastapi import APIRouter, Depends, Header, Response
from redis.asyncio import Redis

from app.api.deps import (
    AuthenticatedClient,
    get_circuit_breakers,
    get_http_client,
    get_rate_limited_client,
    get_redis,
)
from app.core.config import Settings, get_settings
from app.core.exceptions import CircuitOpenError, ProviderError
from app.models.chat import ChatRequest, ChatResponse
from app.services.cache import get_cached_response, set_cached_response
from app.services.circuit_breaker import CircuitBreaker
from app.services.cost_tracker import record_usage
from app.services.idempotency import (
    claim_idempotency_key,
    release_idempotency_key,
    store_idempotent_response,
)
from app.services.resilient_call import call_provider_with_resilience

router = APIRouter()


async def _generate_chat_response(
    provider: str,
    request: ChatRequest,
    response: Response,
    client: AuthenticatedClient,
    settings: Settings,
    http_client: httpx.AsyncClient,
    redis: Redis,
    circuit_breakers: dict[str, CircuitBreaker],
) -> ChatResponse:
    cached_response = await get_cached_response(redis, provider, request)
    if cached_response is not None:
        response.headers["X-Cache"] = "HIT"
        return cached_response

    used_provider = provider
    effective_request = request
    fallback_used = False

    try:
        chat_response = await call_provider_with_resilience(
            provider, request, settings, http_client, circuit_breakers
        )
    except (ProviderError, CircuitOpenError):
        if request.fallback is None:
            raise
        effective_request = request.model_copy(
            update={"model": request.fallback.model, "fallback": None}
        )
        used_provider = request.fallback.provider
        chat_response = await call_provider_with_resilience(
            used_provider, effective_request, settings, http_client, circuit_breakers
        )
        fallback_used = True

    await set_cached_response(
        redis, used_provider, effective_request, chat_response, settings.cache_ttl_seconds
    )
    await record_usage(redis, client.client_id, used_provider, chat_response)
    response.headers["X-Cache"] = "MISS"
    response.headers["X-Fallback"] = "true" if fallback_used else "false"

    return chat_response


@router.post("/chat/{provider}")
async def chat(
    provider: str,
    request: ChatRequest,
    response: Response,
    client: AuthenticatedClient = Depends(get_rate_limited_client),
    settings: Settings = Depends(get_settings),
    http_client: httpx.AsyncClient = Depends(get_http_client),
    redis: Redis = Depends(get_redis),
    circuit_breakers: dict[str, CircuitBreaker] = Depends(get_circuit_breakers),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ChatResponse:
    if idempotency_key is not None:
        existing_response = await claim_idempotency_key(
            redis, client.client_id, idempotency_key, settings.idempotency_lock_ttl_seconds
        )
        if existing_response is not None:
            response.headers["X-Idempotent-Replay"] = "true"
            return existing_response

    try:
        chat_response = await _generate_chat_response(
            provider, request, response, client, settings, http_client, redis, circuit_breakers
        )
    except Exception:
        if idempotency_key is not None:
            await release_idempotency_key(redis, client.client_id, idempotency_key)
        raise

    if idempotency_key is not None:
        await store_idempotent_response(
            redis,
            client.client_id,
            idempotency_key,
            chat_response,
            settings.idempotency_result_ttl_seconds,
        )

    return chat_response
