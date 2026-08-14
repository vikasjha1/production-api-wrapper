import time
from enum import Enum

from app.core.exceptions import CircuitOpenError


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    def __init__(self, failure_threshold: int, recovery_timeout_seconds: float) -> None:
        self._failure_threshold = failure_threshold
        self._recovery_timeout_seconds = recovery_timeout_seconds
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None

    def get_state(self, now: float | None = None) -> CircuitState:
        current_time = now if now is not None else time.time()
        recovery_elapsed = (
            self._opened_at is not None
            and current_time - self._opened_at >= self._recovery_timeout_seconds
        )
        if self._state == CircuitState.OPEN and recovery_elapsed:
            self._state = CircuitState.HALF_OPEN
        return self._state

    def before_call(self, now: float | None = None) -> None:
        if self.get_state(now) == CircuitState.OPEN:
            raise CircuitOpenError("Circuit breaker is open for this provider")

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED
        self._opened_at = None

    def record_failure(self, now: float | None = None) -> None:
        self._failure_count += 1
        if self._state == CircuitState.HALF_OPEN or self._failure_count >= self._failure_threshold:
            self._state = CircuitState.OPEN
            self._opened_at = now if now is not None else time.time()


def get_circuit_breaker(
    breakers: dict[str, CircuitBreaker],
    provider: str,
    failure_threshold: int,
    recovery_timeout_seconds: float,
) -> CircuitBreaker:
    if provider not in breakers:
        breakers[provider] = CircuitBreaker(failure_threshold, recovery_timeout_seconds)
    return breakers[provider]
