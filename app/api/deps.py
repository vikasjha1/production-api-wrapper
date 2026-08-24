from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import httpx
from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import Settings, get_settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.services.circuit_breaker import CircuitBreaker
from app.services.rate_limiter import check_rate_limit

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client  # type: ignore[no-any-return]


def get_redis(request: Request) -> Redis:
    return request.app.state.redis  # type: ignore[no-any-return]


def get_circuit_breakers(request: Request) -> dict[str, CircuitBreaker]:
    return request.app.state.circuit_breakers  # type: ignore[no-any-return]


def get_db_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    return request.app.state.db_session_factory  # type: ignore[no-any-return]


async def get_db_session(
    session_factory: async_sessionmaker[AsyncSession] = Depends(get_db_session_factory),
) -> AsyncGenerator[AsyncSession]:
    async with session_factory() as session:
        yield session


class AuthenticatedClient:
    def __init__(self, client_id: str, allowed_providers: list[str] | None) -> None:
        self.client_id = client_id
        self.allowed_providers = allowed_providers


def get_current_client(
    api_key: str | None = Security(api_key_header),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedClient:
    if api_key is None:
        raise UnauthorizedError("Missing API key")

    client_id = settings.api_keys.get(api_key)
    if client_id is None:
        raise UnauthorizedError("Invalid API key")

    expires_at = settings.api_key_expires_at.get(api_key)
    if expires_at is not None and expires_at < datetime.now(UTC):
        raise UnauthorizedError("API key has expired")

    allowed_providers = settings.api_key_allowed_providers.get(api_key)
    return AuthenticatedClient(client_id=client_id, allowed_providers=allowed_providers)


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


def get_authorized_client(
    provider: str,
    client: AuthenticatedClient = Depends(get_rate_limited_client),
) -> AuthenticatedClient:
    if client.allowed_providers is not None and provider not in client.allowed_providers:
        raise ForbiddenError(f"This API key is not authorized to use provider '{provider}'")
    return client
