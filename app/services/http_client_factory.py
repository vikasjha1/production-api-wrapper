import httpx

from app.core.config import Settings


def build_http_client(settings: Settings) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        limits=httpx.Limits(
            max_connections=settings.http_max_connections,
            max_keepalive_connections=settings.http_max_keepalive_connections,
            keepalive_expiry=settings.http_keepalive_expiry_seconds,
        ),
        timeout=httpx.Timeout(settings.http_timeout_seconds),
    )
