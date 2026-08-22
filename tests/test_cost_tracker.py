import pytest
from fakeredis.aioredis import FakeRedis

from app.models.chat import ChatResponse, ChatUsage
from app.services.cost_tracker import calculate_cost_usd, record_usage


def test_calculate_cost_for_known_model() -> None:
    cost = calculate_cost_usd(
        "anthropic", "claude-haiku-4-5-20251001", input_tokens=1_000_000, output_tokens=1_000_000
    )

    assert cost == pytest.approx(1.00 + 5.00)


def test_calculate_cost_returns_none_for_unknown_provider() -> None:
    cost = calculate_cost_usd("made-up-provider", "some-model", input_tokens=100, output_tokens=100)

    assert cost is None


def test_calculate_cost_returns_none_for_unknown_model() -> None:
    cost = calculate_cost_usd("anthropic", "made-up-model", input_tokens=100, output_tokens=100)

    assert cost is None


def test_calculate_cost_matches_a_dated_model_snapshot_by_prefix() -> None:
    # OpenAI (and others) often respond with a more specific, dated model
    # string than what was requested — e.g. "gpt-4o-mini-2024-07-18" for a
    # request of "gpt-4o-mini". This reproduces exactly that real case.
    cost = calculate_cost_usd(
        "openai", "gpt-4o-mini-2024-07-18", input_tokens=1_000_000, output_tokens=1_000_000
    )

    assert cost == pytest.approx(0.15 + 0.60)


@pytest.mark.asyncio
async def test_record_usage_accumulates_cost_in_redis() -> None:
    redis = FakeRedis()
    response = ChatResponse(
        content="hi",
        model="claude-haiku-4-5-20251001",
        provider="anthropic",
        usage=ChatUsage(input_tokens=1_000_000, output_tokens=0),
    )

    await record_usage(redis, "client-a", "anthropic", response)
    await record_usage(redis, "client-a", "anthropic", response)

    total = await redis.get("cost:client-a")
    assert float(total) == pytest.approx(2.00)


@pytest.mark.asyncio
async def test_record_usage_skips_unknown_model_without_raising() -> None:
    redis = FakeRedis()
    response = ChatResponse(
        content="hi",
        model="unknown-model-xyz",
        provider="anthropic",
        usage=ChatUsage(input_tokens=100, output_tokens=100),
    )

    await record_usage(redis, "client-a", "anthropic", response)

    total = await redis.get("cost:client-a")
    assert total is None
