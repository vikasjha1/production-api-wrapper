import pytest
from fakeredis.aioredis import FakeRedis

from app.core.exceptions import ConflictError
from app.models.chat import ChatResponse, ChatUsage
from app.services.idempotency import (
    claim_idempotency_key,
    release_idempotency_key,
    store_idempotent_response,
)


def make_response() -> ChatResponse:
    return ChatResponse(
        content="Hello there",
        model="claude-haiku-4-5-20251001",
        provider="anthropic",
        usage=ChatUsage(input_tokens=10, output_tokens=3),
    )


@pytest.mark.asyncio
async def test_claiming_a_fresh_key_returns_none() -> None:
    redis = FakeRedis()

    result = await claim_idempotency_key(redis, "client-a", "key-1", lock_ttl_seconds=60)

    assert result is None


@pytest.mark.asyncio
async def test_claiming_an_in_progress_key_raises_conflict() -> None:
    redis = FakeRedis()
    await claim_idempotency_key(redis, "client-a", "key-1", lock_ttl_seconds=60)

    with pytest.raises(ConflictError):
        await claim_idempotency_key(redis, "client-a", "key-1", lock_ttl_seconds=60)


@pytest.mark.asyncio
async def test_completed_key_replays_the_stored_response() -> None:
    redis = FakeRedis()
    await claim_idempotency_key(redis, "client-a", "key-1", lock_ttl_seconds=60)
    await store_idempotent_response(redis, "client-a", "key-1", make_response(), ttl_seconds=86400)

    result = await claim_idempotency_key(redis, "client-a", "key-1", lock_ttl_seconds=60)

    assert result == make_response()


@pytest.mark.asyncio
async def test_releasing_a_key_allows_a_fresh_claim() -> None:
    redis = FakeRedis()
    await claim_idempotency_key(redis, "client-a", "key-1", lock_ttl_seconds=60)

    await release_idempotency_key(redis, "client-a", "key-1")
    result = await claim_idempotency_key(redis, "client-a", "key-1", lock_ttl_seconds=60)

    assert result is None


@pytest.mark.asyncio
async def test_different_clients_do_not_share_the_same_key() -> None:
    redis = FakeRedis()
    await claim_idempotency_key(redis, "client-a", "key-1", lock_ttl_seconds=60)

    result = await claim_idempotency_key(redis, "client-b", "key-1", lock_ttl_seconds=60)

    assert result is None
