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


@pytest.fixture
def configured_client() -> Generator[TestClient, None, None]:
    def override_settings() -> Settings:
        return Settings(
            api_keys={"test-key-abc": "test-client"},
            anthropic_api_key="fake-anthropic-key",
            openai_api_key=None,
            rate_limit_requests=2,
            rate_limit_window_seconds=60,
            retry_max_attempts=3,
            retry_base_delay_seconds=0.01,
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

    # fixture sets rate_limit_requests=2, so the first two should succeed
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
