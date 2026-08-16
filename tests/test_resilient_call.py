import httpx
import pytest
import respx

from app.core.config import Settings
from app.core.exceptions import BadRequestError, CircuitOpenError, ProviderError
from app.models.chat import ChatMessage, ChatRequest
from app.services.circuit_breaker import CircuitBreaker, CircuitState
from app.services.providers.anthropic import ANTHROPIC_API_URL
from app.services.resilient_call import call_provider_with_resilience


def make_settings() -> Settings:
    return Settings(
        anthropic_api_key="fake-anthropic-key",
        retry_max_attempts=1,
        retry_base_delay_seconds=0.01,
        circuit_breaker_failure_threshold=2,
        circuit_breaker_recovery_timeout_seconds=30.0,
    )


def make_request() -> ChatRequest:
    return ChatRequest(
        model="claude-haiku-4-5-20251001", messages=[ChatMessage(role="user", content="hi")]
    )


@pytest.mark.asyncio
@respx.mock
async def test_successful_call_records_success_on_breaker() -> None:
    respx.post(ANTHROPIC_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Hello there"}],
                "model": "claude-haiku-4-5-20251001",
                "usage": {"input_tokens": 10, "output_tokens": 3},
            },
        )
    )
    circuit_breakers: dict[str, CircuitBreaker] = {}

    async with httpx.AsyncClient() as client:
        response = await call_provider_with_resilience(
            "anthropic", make_request(), make_settings(), client, circuit_breakers
        )

    assert response.content == "Hello there"
    assert circuit_breakers["anthropic"].get_state() == CircuitState.CLOSED


@pytest.mark.asyncio
@respx.mock
async def test_provider_failure_records_failure_on_breaker() -> None:
    respx.post(ANTHROPIC_API_URL).mock(
        return_value=httpx.Response(503, json={"error": "overloaded"})
    )
    circuit_breakers: dict[str, CircuitBreaker] = {}

    async with httpx.AsyncClient() as client:
        with pytest.raises(ProviderError):
            await call_provider_with_resilience(
                "anthropic", make_request(), make_settings(), client, circuit_breakers
            )

    # failure_threshold=2 in make_settings(), so one failure shouldn't trip it yet
    assert circuit_breakers["anthropic"].get_state() == CircuitState.CLOSED


@pytest.mark.asyncio
@respx.mock
async def test_bad_request_does_not_affect_breaker() -> None:
    respx.post(ANTHROPIC_API_URL).mock(
        return_value=httpx.Response(400, json={"error": "bad request"})
    )
    circuit_breakers: dict[str, CircuitBreaker] = {}

    async with httpx.AsyncClient() as client:
        with pytest.raises(BadRequestError):
            await call_provider_with_resilience(
                "anthropic", make_request(), make_settings(), client, circuit_breakers
            )

    assert circuit_breakers["anthropic"].get_state() == CircuitState.CLOSED


@pytest.mark.asyncio
@respx.mock
async def test_open_circuit_rejects_without_a_network_call() -> None:
    route = respx.post(ANTHROPIC_API_URL).mock(return_value=httpx.Response(200, json={}))
    circuit_breakers: dict[str, CircuitBreaker] = {
        "anthropic": CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=30.0)
    }
    circuit_breakers["anthropic"].record_failure()

    async with httpx.AsyncClient() as client:
        with pytest.raises(CircuitOpenError):
            await call_provider_with_resilience(
                "anthropic", make_request(), make_settings(), client, circuit_breakers
            )

    assert route.call_count == 0
