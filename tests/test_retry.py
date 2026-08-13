import pytest

from app.core.exceptions import BadRequestError, ProviderError, ProviderTimeoutError
from app.services.retry import with_retry


@pytest.mark.asyncio
async def test_succeeds_immediately_without_retrying() -> None:
    calls = 0

    async def always_succeeds() -> str:
        nonlocal calls
        calls += 1
        return "ok"

    result = await with_retry(always_succeeds, max_attempts=3, base_delay=0.01)

    assert result == "ok"
    assert calls == 1


@pytest.mark.asyncio
async def test_retries_and_eventually_succeeds() -> None:
    calls = 0

    async def fails_twice_then_succeeds() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ProviderTimeoutError("timed out")
        return "ok"

    result = await with_retry(fails_twice_then_succeeds, max_attempts=3, base_delay=0.01)

    assert result == "ok"
    assert calls == 3


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts() -> None:
    calls = 0

    async def always_times_out() -> str:
        nonlocal calls
        calls += 1
        raise ProviderTimeoutError("still timing out")

    with pytest.raises(ProviderTimeoutError):
        await with_retry(always_times_out, max_attempts=3, base_delay=0.01)

    assert calls == 3


@pytest.mark.asyncio
async def test_retries_on_5xx_provider_error() -> None:
    calls = 0

    async def fails_once_with_server_error() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise ProviderError("upstream 503")
        return "ok"

    result = await with_retry(fails_once_with_server_error, max_attempts=3, base_delay=0.01)

    assert result == "ok"
    assert calls == 2


@pytest.mark.asyncio
async def test_does_not_retry_client_errors() -> None:
    calls = 0

    async def bad_request() -> str:
        nonlocal calls
        calls += 1
        raise BadRequestError("invalid model name")

    with pytest.raises(BadRequestError):
        await with_retry(bad_request, max_attempts=3, base_delay=0.01)

    assert calls == 1
