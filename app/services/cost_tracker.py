import logging

from redis.asyncio import Redis

from app.models.chat import ChatResponse

logger = logging.getLogger("app.cost")

# Price per 1M tokens, in USD: (input_price, output_price).
# Manually maintained — providers don't return pricing via their APIs, so
# this needs to be kept in sync by hand whenever a provider changes prices.
PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "anthropic": {
        "claude-haiku-4-5-20251001": (1.00, 5.00),
    },
    "openai": {
        "gpt-4o-mini": (0.15, 0.60),
    },
}


def calculate_cost_usd(
    provider: str, model: str, input_tokens: int, output_tokens: int
) -> float | None:
    provider_pricing = PRICING.get(provider)
    if provider_pricing is None:
        return None

    prices = provider_pricing.get(model)
    if prices is None:
        return None

    input_price_per_million, output_price_per_million = prices
    return (input_tokens / 1_000_000) * input_price_per_million + (
        output_tokens / 1_000_000
    ) * output_price_per_million


async def record_usage(redis: Redis, client_id: str, provider: str, response: ChatResponse) -> None:
    cost = calculate_cost_usd(
        provider, response.model, response.usage.input_tokens, response.usage.output_tokens
    )

    if cost is None:
        logger.warning(
            "No pricing data for %s/%s — cost not tracked",
            provider,
            response.model,
        )
        return

    logger.info(
        "chat_cost",
        extra={
            "client_id": client_id,
            "provider": provider,
            "model": response.model,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cost_usd": round(cost, 6),
        },
    )

    await redis.incrbyfloat(f"cost:{client_id}", cost)
