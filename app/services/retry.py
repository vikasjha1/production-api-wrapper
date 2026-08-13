import asyncio
import logging
import random
from collections.abc import Awaitable, Callable

from app.core.exceptions import ProviderError, ProviderTimeoutError

logger = logging.getLogger("app.retry")


def _is_retryable(exc: Exception) -> bool:
    if isinstance(exc, ProviderTimeoutError):
        return True
    if isinstance(exc, ProviderError):
        return exc.status_code >= 500
    return False


async def with_retry[T](
    func: Callable[[], Awaitable[T]],
    max_attempts: int = 3,
    base_delay: float = 0.5,
) -> T:
    for attempt in range(1, max_attempts + 1):
        try:
            return await func()
        except Exception as exc:
            if not _is_retryable(exc) or attempt == max_attempts:
                raise

            delay = base_delay * (2 ** (attempt - 1))
            jitter = random.uniform(0, delay * 0.1)
            sleep_time = delay + jitter

            logger.warning(
                "retrying_after_failure",
                extra={
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "delay_seconds": round(sleep_time, 3),
                    "error": str(exc),
                },
            )
            await asyncio.sleep(sleep_time)

    raise AssertionError("unreachable: loop above always returns or raises")
