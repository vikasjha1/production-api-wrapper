import httpx
from fastapi import APIRouter, Depends

from app.api.deps import AuthenticatedClient, get_current_client, get_http_client
from app.core.config import Settings, get_settings
from app.models.chat import ChatRequest, ChatResponse
from app.services.providers.registry import get_provider

router = APIRouter()


@router.post("/chat/{provider}")
async def chat(
    provider: str,
    request: ChatRequest,
    client: AuthenticatedClient = Depends(get_current_client),
    settings: Settings = Depends(get_settings),
    http_client: httpx.AsyncClient = Depends(get_http_client),
) -> ChatResponse:
    provider_instance = get_provider(provider, settings, http_client)
    return await provider_instance.send_message(request)
