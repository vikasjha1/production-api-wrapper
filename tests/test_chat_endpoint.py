from collections.abc import Generator

import httpx
import pytest
import respx
from fakeredis.aioredis import FakeRedis
from fastapi.testclient import TestClient

from app.api.deps import get_redis
from app.core.config import Settings, get_settings
from app.main import app
from app.services.providers.anthropic import ANTHROPIC_API_URL
from app.services.providers.openai import OPENAI_API_URL


@pytest.fixture
def configured_client() -> Generator[TestClient, None, None]:
    def override_settings() -> Settings:
        return Settings(
            api_keys={"test-key-abc": "test-client"},
            anthropic_api_key="fake-anthropic-key",
            openai_api_key=None,
            # Generous defaults so most tests never brush up against these
            # limits by accident. Tests that specifically exercise rate
            # limiting or the circuit breaker override get_settings locally
            # with tighter values instead of changing this shared default.
            rate_limit_requests=100,
            rate_limit_window_seconds=60,
            retry_max_attempts=3,
            retry_base_delay_seconds=0.01,
            circuit_breaker_failure_threshold=100,
            circuit_breaker_recovery_timeout_seconds=30.0,
            idempotency_lock_ttl_seconds=60,
            idempotency_result_ttl_seconds=86400,
        )

    fake_redis = FakeRedis()

    app.dependency_overrides[get_settings] = override_settings
    app.dependency_overrides[get_redis] = lambda: fake_redis
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.pop(get_settings, None)
    app.dependency_overrides.pop(get_redis, None)


@respx.mock
def test_chat_with_anthropic_returns_response(configured_client: TestClient) -> None:
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

    response = configured_client.post(
        "/v1/chat/anthropic",
        headers={"X-API-Key": "test-key-abc"},
        json={
            "model": "claude-haiku-4-5-20251001",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["content"] == "Hello there"
    assert body["provider"] == "anthropic"


def test_chat_requires_auth(configured_client: TestClient) -> None:
    response = configured_client.post(
        "/v1/chat/anthropic",
        json={
            "model": "claude-haiku-4-5-20251001",
            "messages": [{"role": "user", "content": "hi"}],
        },
    )

    assert response.status_code == 401


def test_chat_rejects_unknown_provider(configured_client: TestClient) -> None:
    response = configured_client.post(
        "/v1/chat/not-a-real-provider",
        headers={"X-API-Key": "test-key-abc"},
        json={"model": "x", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 400


def test_chat_rejects_unconfigured_provider(configured_client: TestClient) -> None:
    response = configured_client.post(
        "/v1/chat/openai",
        headers={"X-API-Key": "test-key-abc"},
        json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "hi"}]},
    )

    assert response.status_code == 400


@respx.mock
def test_chat_returns_429_after_rate_limit_exceeded(configured_client: TestClient) -> None:
    def restrictive_rate_limit_settings() -> Settings:
        return Settings(
            api_keys={"test-key-abc": "test-client"},
            anthropic_api_key="fake-anthropic-key",
            openai_api_key=None,
            rate_limit_requests=2,
            rate_limit_window_seconds=60,
            retry_max_attempts=3,
            retry_base_delay_seconds=0.01,
            circuit_breaker_failure_threshold=100,
            circuit_breaker_recovery_timeout_seconds=30.0,
        )

    app.dependency_overrides[get_settings] = restrictive_rate_limit_settings

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

    headers = {"X-API-Key": "test-key-abc"}
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "messages": [{"role": "user", "content": "hi"}],
    }

    # overridden settings set rate_limit_requests=2, so the first two succeed
    first = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)
    second = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)
    third = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert third.status_code == 429
    assert third.json()["error"]["code"] == "rate_limit_exceeded"


@respx.mock
def test_identical_chat_request_is_served_from_cache(configured_client: TestClient) -> None:
    route = respx.post(ANTHROPIC_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Hello there"}],
                "model": "claude-haiku-4-5-20251001",
                "usage": {"input_tokens": 10, "output_tokens": 3},
            },
        )
    )

    headers = {"X-API-Key": "test-key-abc"}
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "messages": [{"role": "user", "content": "hi"}],
    }

    first = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)
    second = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)

    assert first.status_code == 200
    assert first.headers["X-Cache"] == "MISS"
    assert second.status_code == 200
    assert second.headers["X-Cache"] == "HIT"
    assert second.json() == first.json()

    # The real proof: Anthropic was only actually called once, even though
    # we made two identical requests through the route.
    assert route.call_count == 1


@respx.mock
def test_chat_records_cost_and_cache_hits_dont_double_count(configured_client: TestClient) -> None:
    respx.post(ANTHROPIC_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Hello there"}],
                "model": "claude-haiku-4-5-20251001",
                "usage": {"input_tokens": 1_000_000, "output_tokens": 0},
            },
        )
    )

    headers = {"X-API-Key": "test-key-abc"}
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "messages": [{"role": "user", "content": "cost check"}],
    }

    first = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)
    second = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)

    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"

    usage_response = configured_client.get("/v1/usage", headers=headers)

    assert usage_response.status_code == 200
    # 1,000,000 input tokens at $1.00/1M = $1.00 — counted once, not twice,
    # since the second call was served from cache.
    assert usage_response.json()["total_cost_usd"] == pytest.approx(1.00)


@respx.mock
def test_chat_retries_on_transient_provider_error_and_succeeds(
    configured_client: TestClient,
) -> None:
    route = respx.post(ANTHROPIC_API_URL).mock(
        side_effect=[
            httpx.Response(503, json={"error": "overloaded"}),
            httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "Hello there"}],
                    "model": "claude-haiku-4-5-20251001",
                    "usage": {"input_tokens": 10, "output_tokens": 3},
                },
            ),
        ]
    )

    response = configured_client.post(
        "/v1/chat/anthropic",
        headers={"X-API-Key": "test-key-abc"},
        json={
            "model": "claude-haiku-4-5-20251001",
            "messages": [{"role": "user", "content": "retry check"}],
        },
    )

    assert response.status_code == 200
    assert response.json()["content"] == "Hello there"
    # Proves the client only saw one final answer, even though the first
    # attempt against Anthropic actually failed with a 503 underneath.
    assert route.call_count == 2


@respx.mock
def test_chat_circuit_opens_after_repeated_failures(configured_client: TestClient) -> None:
    def strict_breaker_settings() -> Settings:
        return Settings(
            api_keys={"test-key-abc": "test-client"},
            anthropic_api_key="fake-anthropic-key",
            openai_api_key=None,
            rate_limit_requests=100,
            rate_limit_window_seconds=60,
            retry_max_attempts=1,
            retry_base_delay_seconds=0.01,
            circuit_breaker_failure_threshold=2,
            circuit_breaker_recovery_timeout_seconds=30.0,
        )

    app.dependency_overrides[get_settings] = strict_breaker_settings

    route = respx.post(ANTHROPIC_API_URL).mock(
        return_value=httpx.Response(503, json={"error": "overloaded"})
    )

    headers = {"X-API-Key": "test-key-abc"}
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "messages": [{"role": "user", "content": "circuit check"}],
    }

    # Two failures in a row should trip the breaker (threshold=2).
    first = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)
    second = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)

    assert first.status_code == 502
    assert second.status_code == 502
    calls_before_open = route.call_count

    third = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)

    assert third.status_code == 503
    assert third.json()["error"]["code"] == "circuit_open"
    # The real proof: the third request never even reached Anthropic —
    # the breaker rejected it before any network call was attempted.
    assert route.call_count == calls_before_open


@respx.mock
def test_chat_client_errors_do_not_trip_the_circuit_breaker(configured_client: TestClient) -> None:
    def strict_breaker_settings() -> Settings:
        return Settings(
            api_keys={"test-key-abc": "test-client"},
            anthropic_api_key="fake-anthropic-key",
            openai_api_key=None,
            rate_limit_requests=100,
            rate_limit_window_seconds=60,
            retry_max_attempts=1,
            retry_base_delay_seconds=0.01,
            circuit_breaker_failure_threshold=2,
            circuit_breaker_recovery_timeout_seconds=30.0,
        )

    app.dependency_overrides[get_settings] = strict_breaker_settings

    respx.post(ANTHROPIC_API_URL).mock(
        return_value=httpx.Response(400, json={"error": "invalid request"})
    )

    headers = {"X-API-Key": "test-key-abc"}
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "messages": [{"role": "user", "content": "malformed on purpose"}],
    }

    # Same failure threshold (2) as the circuit-breaker test above, but these
    # are client mistakes (4xx), not provider health problems — three of
    # them in a row should NOT trip the breaker.
    first = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)
    second = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)
    third = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)

    assert first.status_code == 400
    assert second.status_code == 400
    # If the breaker had incorrectly tripped, this would be 503/circuit_open
    # instead of another honest 400.
    assert third.status_code == 400
    assert third.json()["error"]["code"] == "bad_request"


def _fallback_settings() -> Settings:
    return Settings(
        api_keys={"test-key-abc": "test-client"},
        anthropic_api_key="fake-anthropic-key",
        openai_api_key="fake-openai-key",
        rate_limit_requests=100,
        rate_limit_window_seconds=60,
        retry_max_attempts=1,
        retry_base_delay_seconds=0.01,
        circuit_breaker_failure_threshold=100,
        circuit_breaker_recovery_timeout_seconds=30.0,
    )


@respx.mock
def test_chat_falls_back_to_secondary_provider_when_primary_fails(
    configured_client: TestClient,
) -> None:
    app.dependency_overrides[get_settings] = _fallback_settings

    respx.post(ANTHROPIC_API_URL).mock(
        return_value=httpx.Response(503, json={"error": "overloaded"})
    )
    openai_route = respx.post(OPENAI_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2026-01-01",
                "choices": [{"message": {"role": "assistant", "content": "Hi from OpenAI"}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 4},
            },
        )
    )

    response = configured_client.post(
        "/v1/chat/anthropic",
        headers={"X-API-Key": "test-key-abc"},
        json={
            "model": "claude-haiku-4-5-20251001",
            "messages": [{"role": "user", "content": "fallback check"}],
            "fallback": {"provider": "openai", "model": "gpt-4o-mini"},
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "openai"
    assert body["content"] == "Hi from OpenAI"
    assert response.headers["X-Fallback"] == "true"
    assert openai_route.call_count == 1


@respx.mock
def test_chat_without_fallback_field_fails_normally(configured_client: TestClient) -> None:
    app.dependency_overrides[get_settings] = _fallback_settings

    respx.post(ANTHROPIC_API_URL).mock(
        return_value=httpx.Response(503, json={"error": "overloaded"})
    )
    openai_route = respx.post(OPENAI_API_URL).mock(return_value=httpx.Response(200, json={}))

    response = configured_client.post(
        "/v1/chat/anthropic",
        headers={"X-API-Key": "test-key-abc"},
        json={
            "model": "claude-haiku-4-5-20251001",
            "messages": [{"role": "user", "content": "no fallback configured"}],
        },
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_error"
    # OpenAI should never have been contacted at all — no fallback was requested.
    assert openai_route.call_count == 0


@respx.mock
def test_chat_fallback_also_failing_returns_its_own_error(configured_client: TestClient) -> None:
    app.dependency_overrides[get_settings] = _fallback_settings

    respx.post(ANTHROPIC_API_URL).mock(
        return_value=httpx.Response(503, json={"error": "overloaded"})
    )
    respx.post(OPENAI_API_URL).mock(return_value=httpx.Response(503, json={"error": "also down"}))

    response = configured_client.post(
        "/v1/chat/anthropic",
        headers={"X-API-Key": "test-key-abc"},
        json={
            "model": "claude-haiku-4-5-20251001",
            "messages": [{"role": "user", "content": "both down"}],
            "fallback": {"provider": "openai", "model": "gpt-4o-mini"},
        },
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_error"


@respx.mock
def test_chat_idempotent_replay_skips_second_provider_call(configured_client: TestClient) -> None:
    route = respx.post(ANTHROPIC_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Hello there"}],
                "model": "claude-haiku-4-5-20251001",
                "usage": {"input_tokens": 10, "output_tokens": 3},
            },
        )
    )

    headers = {"X-API-Key": "test-key-abc", "Idempotency-Key": "retry-key-123"}
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "messages": [{"role": "user", "content": "idempotency check"}],
    }

    first = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)
    second = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)

    assert first.status_code == 200
    assert "X-Idempotent-Replay" not in first.headers
    assert second.status_code == 200
    assert second.headers["X-Idempotent-Replay"] == "true"
    assert second.json() == first.json()

    # The real proof: Anthropic was only actually contacted once.
    assert route.call_count == 1


@respx.mock
def test_chat_failed_attempt_releases_idempotency_key_for_retry(
    configured_client: TestClient,
) -> None:
    def single_attempt_settings() -> Settings:
        return Settings(
            api_keys={"test-key-abc": "test-client"},
            anthropic_api_key="fake-anthropic-key",
            openai_api_key=None,
            rate_limit_requests=100,
            rate_limit_window_seconds=60,
            retry_max_attempts=1,
            retry_base_delay_seconds=0.01,
            circuit_breaker_failure_threshold=100,
            circuit_breaker_recovery_timeout_seconds=30.0,
            idempotency_lock_ttl_seconds=60,
            idempotency_result_ttl_seconds=86400,
        )

    app.dependency_overrides[get_settings] = single_attempt_settings

    route = respx.post(ANTHROPIC_API_URL).mock(
        side_effect=[
            httpx.Response(503, json={"error": "overloaded"}),
            httpx.Response(
                200,
                json={
                    "content": [{"type": "text", "text": "Recovered"}],
                    "model": "claude-haiku-4-5-20251001",
                    "usage": {"input_tokens": 10, "output_tokens": 3},
                },
            ),
        ]
    )

    headers = {"X-API-Key": "test-key-abc", "Idempotency-Key": "retry-after-failure"}
    payload = {
        "model": "claude-haiku-4-5-20251001",
        "messages": [{"role": "user", "content": "will fail then succeed"}],
    }

    first = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)
    second = configured_client.post("/v1/chat/anthropic", headers=headers, json=payload)

    assert first.status_code == 502
    # If the lock hadn't been released after the failure, this would come
    # back 409 (conflict) instead of a genuine fresh 200.
    assert second.status_code == 200
    assert second.json()["content"] == "Recovered"
    assert route.call_count == 2
