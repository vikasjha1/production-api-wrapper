import time

from redis.asyncio import Redis

from app.core.exceptions import RateLimitExceededError


async def check_rate_limit(
    redis: Redis,
    client_id: str,
    limit: int,
    window_seconds: int,
    now: float | None = None,
) -> None:
    current_time = now if now is not None else time.time()
    current_window = int(current_time // window_seconds)
    previous_window = current_window - 1

    current_key = f"ratelimit:{client_id}:{current_window}"
    previous_key = f"ratelimit:{client_id}:{previous_window}"

    current_count = await redis.incr(current_key)
    if current_count == 1:
        await redis.expire(current_key, window_seconds * 2)

    previous_count_raw = await redis.get(previous_key)
    previous_count = int(previous_count_raw) if previous_count_raw else 0

    elapsed_in_current = current_time % window_seconds
    weight_of_previous = max(0.0, (window_seconds - elapsed_in_current) / window_seconds)

    weighted_count = previous_count * weight_of_previous + current_count

    if weighted_count > limit:
        raise RateLimitExceededError(f"Rate limit exceeded: {limit} requests per {window_seconds}s")
