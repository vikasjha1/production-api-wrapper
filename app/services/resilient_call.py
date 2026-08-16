import httpx

from app.core.config import Settings
from app.core.exceptions import ProviderError
from app.models.chat import ChatRequest, ChatResponse
from app.services.circuit_breaker import CircuitBreaker, get_circuit_breaker
from app.services.providers.registry import get_provider
from app.services.retry import with_retry


async def call_provider_with_resilience(
    provider_name: str,
    request: ChatRequest,
    settings: Settings,
    http_client: httpx.AsyncClient,
    circuit_breakers: dict[str, CircuitBreaker],
) -> ChatResponse:
    provider_instance = get_provider(provider_name, settings, http_client)

    breaker = get_circuit_breaker(
        circuit_breakers,
        provider_name,
        settings.circuit_breaker_failure_threshold,
        settings.circuit_breaker_recovery_timeout_seconds,
    )
    breaker.before_call()

    try:
        chat_response = await with_retry(
            lambda: provider_instance.send_message(request),
            max_attempts=settings.retry_max_attempts,
            base_delay=settings.retry_base_delay_seconds,
        )
    except ProviderError:
        breaker.record_failure()
        raise
    else:
        breaker.record_success()

    return chat_response
