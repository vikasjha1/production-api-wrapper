import pytest

from app.core.exceptions import CircuitOpenError
from app.services.circuit_breaker import CircuitBreaker, CircuitState, get_circuit_breaker


def test_starts_closed() -> None:
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout_seconds=30)

    assert breaker.get_state() == CircuitState.CLOSED
    breaker.before_call()


def test_stays_closed_below_failure_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout_seconds=30)

    breaker.record_failure(now=100.0)
    breaker.record_failure(now=100.0)

    assert breaker.get_state(now=100.0) == CircuitState.CLOSED


def test_opens_after_reaching_failure_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout_seconds=30)

    breaker.record_failure(now=100.0)
    breaker.record_failure(now=100.0)
    breaker.record_failure(now=100.0)

    assert breaker.get_state(now=100.0) == CircuitState.OPEN


def test_before_call_raises_when_open() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=30)
    breaker.record_failure(now=100.0)

    with pytest.raises(CircuitOpenError):
        breaker.before_call(now=100.0)


def test_moves_to_half_open_after_recovery_timeout() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=30)
    breaker.record_failure(now=100.0)

    assert breaker.get_state(now=100.0) == CircuitState.OPEN
    assert breaker.get_state(now=131.0) == CircuitState.HALF_OPEN


def test_half_open_success_closes_the_circuit() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=30)
    breaker.record_failure(now=100.0)
    breaker.get_state(now=131.0)  # crosses into HALF_OPEN

    breaker.record_success()

    assert breaker.get_state(now=131.0) == CircuitState.CLOSED


def test_half_open_failure_reopens_the_circuit() -> None:
    breaker = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=30)
    breaker.record_failure(now=100.0)
    breaker.get_state(now=131.0)  # crosses into HALF_OPEN

    breaker.record_failure(now=131.0)

    assert breaker.get_state(now=131.0) == CircuitState.OPEN


def test_registry_reuses_the_same_breaker_for_a_provider() -> None:
    breakers: dict[str, CircuitBreaker] = {}

    first = get_circuit_breaker(
        breakers, "anthropic", failure_threshold=3, recovery_timeout_seconds=30
    )
    second = get_circuit_breaker(
        breakers, "anthropic", failure_threshold=3, recovery_timeout_seconds=30
    )

    assert first is second


def test_registry_tracks_providers_independently() -> None:
    breakers: dict[str, CircuitBreaker] = {}

    anthropic_breaker = get_circuit_breaker(
        breakers, "anthropic", failure_threshold=1, recovery_timeout_seconds=30
    )
    openai_breaker = get_circuit_breaker(
        breakers, "openai", failure_threshold=1, recovery_timeout_seconds=30
    )

    anthropic_breaker.record_failure(now=100.0)

    assert anthropic_breaker.get_state(now=100.0) == CircuitState.OPEN
    assert openai_breaker.get_state(now=100.0) == CircuitState.CLOSED
