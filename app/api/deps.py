import httpx
from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader
from redis.asyncio import Redis

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError
from app.services.circuit_breaker import CircuitBreaker
from app.services.rate_limiter import check_rate_limit

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client  # type: ignore[no-any-return]


def get_redis(request: Request) -> Redis:
    return request.app.state.redis  # type: ignore[no-any-return]


def get_circuit_breakers(request: Request) -> dict[str, CircuitBreaker]:
    return request.app.state.circuit_breakers  # type: ignore[no-any-return]


class AuthenticatedClient:
    def __init__(self, client_id: str) -> None:
        self.client_id = client_id


def get_current_client(
    api_key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedClient:
    if api_key is None:
        raise UnauthorizedError("Missing API key")

    client_id = settings.api_keys.get(api_key)
    if client_id is None:
        raise UnauthorizedError("Invalid API key")

    return AuthenticatedClient(client_id=client_id)


async def get_rate_limited_client(
    client: AuthenticatedClient = Depends(get_current_client),
    redis: Redis = Depends(get_redis),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedClient:
    await check_rate_limit(
        redis=redis,
        client_id=client.client_id,
        limit=settings.rate_limit_requests,
        window_seconds=settings.rate_limit_window_seconds,
    )
    return client
