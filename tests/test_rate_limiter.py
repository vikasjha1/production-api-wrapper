import pytest
from fakeredis.aioredis import FakeRedis

from app.core.exceptions import RateLimitExceededError
from app.services.rate_limiter import check_rate_limit


@pytest.mark.asyncio
async def test_allows_requests_up_to_the_limit() -> None:
    redis = FakeRedis()

    for _ in range(3):
        await check_rate_limit(redis, client_id="client-a", limit=3, window_seconds=60, now=100.0)


@pytest.mark.asyncio
async def test_rejects_requests_over_the_limit() -> None:
    redis = FakeRedis()

    for _ in range(3):
        await check_rate_limit(redis, client_id="client-a", limit=3, window_seconds=60, now=100.0)

    with pytest.raises(RateLimitExceededError):
        await check_rate_limit(redis, client_id="client-a", limit=3, window_seconds=60, now=100.0)


@pytest.mark.asyncio
async def test_limits_are_tracked_separately_per_client() -> None:
    redis = FakeRedis()

    for _ in range(3):
        await check_rate_limit(redis, client_id="client-a", limit=3, window_seconds=60, now=100.0)

    # client-b has made no requests yet, so their own limit is unaffected
    await check_rate_limit(redis, client_id="client-b", limit=3, window_seconds=60, now=100.0)


@pytest.mark.asyncio
async def test_burst_across_a_window_boundary_is_rejected() -> None:
    """Reproduces the exact fixed-window boundary problem: 60 requests right at
    the end of one window, then 60 more right at the start of the next, should
    NOT both succeed just because they landed in two different fixed windows.
    """
    redis = FakeRedis()
    window_seconds = 60
    limit = 60

    # Window 1 spans [60, 120). Send the full limit right at the end of it.
    end_of_window_1 = 119.9
    for _ in range(limit):
        await check_rate_limit(
            redis,
            client_id="client-a",
            limit=limit,
            window_seconds=window_seconds,
            now=end_of_window_1,
        )

    # Window 2 starts at 120. This request lands a fraction of a second later,
    # so almost none of window 1's traffic has "faded out" yet.
    start_of_window_2 = 120.05
    with pytest.raises(RateLimitExceededError):
        await check_rate_limit(
            redis,
            client_id="client-a",
            limit=limit,
            window_seconds=window_seconds,
            now=start_of_window_2,
        )


@pytest.mark.asyncio
async def test_capacity_reopens_as_the_window_progresses() -> None:
    """As more of the new window elapses, the previous window's weight decays,
    so capacity genuinely frees back up instead of staying blocked forever.
    """
    redis = FakeRedis()
    window_seconds = 60
    limit = 60

    end_of_window_1 = 119.9
    for _ in range(limit):
        await check_rate_limit(
            redis,
            client_id="client-a",
            limit=limit,
            window_seconds=window_seconds,
            now=end_of_window_1,
        )

    # Near the END of window 2, window 1's contribution has almost fully decayed,
    # so a request here should succeed even though window 1 was completely full.
    near_end_of_window_2 = 179.0
    await check_rate_limit(
        redis,
        client_id="client-a",
        limit=limit,
        window_seconds=window_seconds,
        now=near_end_of_window_2,
    )
