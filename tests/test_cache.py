import pytest
from fakeredis.aioredis import FakeRedis

from app.models.chat import ChatMessage, ChatRequest, ChatResponse, ChatUsage
from app.services.cache import _build_cache_key, get_cached_response, set_cached_response


def make_request(content: str = "hi") -> ChatRequest:
    return ChatRequest(
        model="claude-haiku-4-5-20251001",
        messages=[ChatMessage(role="user", content=content)],
    )


def make_response() -> ChatResponse:
    return ChatResponse(
        content="Hello there",
        model="claude-haiku-4-5-20251001",
        provider="anthropic",
        usage=ChatUsage(input_tokens=10, output_tokens=3),
    )


@pytest.mark.asyncio
async def test_miss_when_nothing_cached() -> None:
    redis = FakeRedis()

    cached = await get_cached_response(redis, "anthropic", make_request())

    assert cached is None


@pytest.mark.asyncio
async def test_set_then_get_returns_the_same_response() -> None:
    redis = FakeRedis()
    request = make_request()
    response = make_response()

    await set_cached_response(redis, "anthropic", request, response, ttl_seconds=60)
    cached = await get_cached_response(redis, "anthropic", request)

    assert cached == response


@pytest.mark.asyncio
async def test_different_request_content_is_not_a_cache_hit() -> None:
    redis = FakeRedis()

    await set_cached_response(
        redis, "anthropic", make_request("hi"), make_response(), ttl_seconds=60
    )
    cached = await get_cached_response(redis, "anthropic", make_request("something else entirely"))

    assert cached is None


@pytest.mark.asyncio
async def test_different_provider_is_not_a_cache_hit() -> None:
    redis = FakeRedis()
    request = make_request()

    await set_cached_response(redis, "anthropic", request, make_response(), ttl_seconds=60)
    cached = await get_cached_response(redis, "openai", request)

    assert cached is None


@pytest.mark.asyncio
async def test_sets_a_ttl_on_the_cached_entry() -> None:
    redis = FakeRedis()
    request = make_request()

    await set_cached_response(redis, "anthropic", request, make_response(), ttl_seconds=60)

    ttl = await redis.ttl(_build_cache_key("anthropic", request))
    assert 0 < ttl <= 60
