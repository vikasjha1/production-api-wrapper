import httpx

from app.core.config import Settings
from app.core.exceptions import BadRequestError
from app.services.providers.anthropic import AnthropicProvider
from app.services.providers.base import Provider
from app.services.providers.openai import OpenAIProvider


def get_provider(provider_name: str, settings: Settings, client: httpx.AsyncClient) -> Provider:
    if provider_name == "anthropic":
        if not settings.anthropic_api_key:
            raise BadRequestError("Anthropic is not configured on this gateway")
        return AnthropicProvider(api_key=settings.anthropic_api_key, client=client)

    if provider_name == "openai":
        if not settings.openai_api_key:
            raise BadRequestError("OpenAI is not configured on this gateway")
        return OpenAIProvider(api_key=settings.openai_api_key, client=client)

    raise BadRequestError(f"Unknown provider: {provider_name}")
