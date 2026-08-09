from fastapi import Depends, Security
from fastapi.security import APIKeyHeader

from app.core.config import Settings, get_settings
from app.core.exceptions import UnauthorizedError

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


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
