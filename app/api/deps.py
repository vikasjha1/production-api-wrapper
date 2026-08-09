import httpx
from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_http_client(request: Request) -> httpx.AsyncClient:
    return request.app.state.http_client  # type: ignore[no-any-return]


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
