import logging
import time
from dataclasses import dataclass

import httpx
from fastapi import APIRouter, Depends, Header, Response
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    AuthenticatedClient,
    get_authorized_client,
    get_circuit_breakers,
    get_db_session,
    get_http_client,
    get_redis,
)
from app.core.config import Settings, get_settings
from app.core.context import request_id_ctx
from app.core.exceptions import CircuitOpenError, GatewayError, ProviderError
from app.models.chat import ChatRequest, ChatResponse
from app.services.audit_log import write_audit_log
from app.services.cache import get_cached_response, set_cached_response
from app.services.circuit_breaker import CircuitBreaker
from app.services.cost_tracker import calculate_cost_usd, record_usage
from app.services.idempotency import (
    claim_idempotency_key,
    release_idempotency_key,
    store_idempotent_response,
)
from app.services.prompt_injection import detect_prompt_injection_risk
from app.services.resilient_call import call_provider_with_resilience

router = APIRouter()

logger = logging.getLogger("app.audit")


@dataclass
class ChatOutcome:
    response: ChatResponse
    used_provider: str
    cache_hit: bool
    fallback_used: bool


async def _generate_chat_response(
    provider: str,
    request: ChatRequest,
    client: AuthenticatedClient,
    settings: Settings,
    http_client: httpx.AsyncClient,
    redis: Redis,
    circuit_breakers: dict[str, CircuitBreaker],
) -> ChatOutcome:
    cached_response = await get_cached_response(redis, provider, request)
    if cached_response is not None:
        return ChatOutcome(
            response=cached_response, used_provider=provider, cache_hit=True, fallback_used=False
        )

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

    return ChatOutcome(
        response=chat_response,
        used_provider=used_provider,
        cache_hit=False,
        fallback_used=fallback_used,
    )


async def _safe_write_audit_log(
    db_session: AsyncSession,
    *,
    start_time: float,
    request_id: str,
    client_id: str,
    provider: str,
    used_provider: str,
    model: str,
    status: str,
    error_code: str | None,
    status_code: int,
    cache_hit: bool,
    fallback_used: bool,
    input_tokens: int | None,
    output_tokens: int | None,
    cost_usd: float | None,
    prompt_injection_suspected: bool,
) -> None:
    latency_ms = (time.perf_counter() - start_time) * 1000
    try:
        await write_audit_log(
            db_session,
            request_id=request_id,
            client_id=client_id,
            provider=provider,
            used_provider=used_provider,
            model=model,
            status=status,
            error_code=error_code,
            status_code=status_code,
            cache_hit=cache_hit,
            fallback_used=fallback_used,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            prompt_injection_suspected=prompt_injection_suspected,
        )
    except Exception:
        logger.warning("Failed to write audit log entry", exc_info=True)


@router.post("/chat/{provider}")
async def chat(
    provider: str,
    request: ChatRequest,
    response: Response,
    client: AuthenticatedClient = Depends(get_authorized_client),
    settings: Settings = Depends(get_settings),
    http_client: httpx.AsyncClient = Depends(get_http_client),
    redis: Redis = Depends(get_redis),
    circuit_breakers: dict[str, CircuitBreaker] = Depends(get_circuit_breakers),
    db_session: AsyncSession = Depends(get_db_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> ChatResponse:
    if idempotency_key is not None:
        existing_response = await claim_idempotency_key(
            redis, client.client_id, idempotency_key, settings.idempotency_lock_ttl_seconds
        )
        if existing_response is not None:
            response.headers["X-Idempotent-Replay"] = "true"
            return existing_response

    start_time = time.perf_counter()
    request_id = request_id_ctx.get()
    prompt_injection_suspected = detect_prompt_injection_risk(request.messages)

    try:
        outcome = await _generate_chat_response(
            provider, request, client, settings, http_client, redis, circuit_breakers
        )
    except Exception as exc:
        if idempotency_key is not None:
            await release_idempotency_key(redis, client.client_id, idempotency_key)

        error_code = exc.error_code if isinstance(exc, GatewayError) else "internal_error"
        status_code = exc.status_code if isinstance(exc, GatewayError) else 500
        await _safe_write_audit_log(
            db_session,
            start_time=start_time,
            request_id=request_id,
            client_id=client.client_id,
            provider=provider,
            used_provider=provider,
            model=request.model,
            status="error",
            error_code=error_code,
            status_code=status_code,
            cache_hit=False,
            fallback_used=False,
            input_tokens=None,
            output_tokens=None,
            cost_usd=None,
            prompt_injection_suspected=prompt_injection_suspected,
        )
        raise

    response.headers["X-Cache"] = "HIT" if outcome.cache_hit else "MISS"
    response.headers["X-Fallback"] = "true" if outcome.fallback_used else "false"
    if prompt_injection_suspected:
        response.headers["X-Prompt-Injection-Suspected"] = "true"

    if idempotency_key is not None:
        await store_idempotent_response(
            redis,
            client.client_id,
            idempotency_key,
            outcome.response,
            settings.idempotency_result_ttl_seconds,
        )

    cost_usd = calculate_cost_usd(
        outcome.used_provider,
        outcome.response.model,
        outcome.response.usage.input_tokens,
        outcome.response.usage.output_tokens,
    )
    await _safe_write_audit_log(
        db_session,
        start_time=start_time,
        request_id=request_id,
        client_id=client.client_id,
        provider=provider,
        used_provider=outcome.used_provider,
        model=outcome.response.model,
        status="success",
        error_code=None,
        status_code=200,
        cache_hit=outcome.cache_hit,
        fallback_used=outcome.fallback_used,
        input_tokens=outcome.response.usage.input_tokens,
        output_tokens=outcome.response.usage.output_tokens,
        cost_usd=cost_usd,
        prompt_injection_suspected=prompt_injection_suspected,
    )

    return outcome.response
