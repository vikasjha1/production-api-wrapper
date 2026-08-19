import httpx

from app.core.config import Settings
from app.services.http_client_factory import build_http_client


def test_build_http_client_returns_an_async_client() -> None:
    settings = Settings()

    client = build_http_client(settings)

    assert isinstance(client, httpx.AsyncClient)


def test_build_http_client_applies_the_configured_timeout() -> None:
    settings = Settings(http_timeout_seconds=12.5)

    client = build_http_client(settings)

    assert client.timeout == httpx.Timeout(12.5)


def test_build_http_client_uses_default_timeout_when_unset() -> None:
    settings = Settings()

    client = build_http_client(settings)

    assert client.timeout == httpx.Timeout(30.0)
