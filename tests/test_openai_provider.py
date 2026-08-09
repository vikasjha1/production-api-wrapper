import httpx
import pytest
import respx

from app.core.exceptions import ProviderError, ProviderTimeoutError
from app.models.chat import ChatMessage, ChatRequest
from app.services.providers.openai import OPENAI_API_URL, OpenAIProvider


@pytest.mark.asyncio
@respx.mock
async def test_send_message_parses_successful_response() -> None:
    respx.post(OPENAI_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini-2026-01-01",
                "choices": [{"message": {"role": "assistant", "content": "Hello there"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 3},
            },
        )
    )

    async with httpx.AsyncClient() as client:
        provider = OpenAIProvider(api_key="fake-key", client=client)
        response = await provider.send_message(
            ChatRequest(model="gpt-4o-mini", messages=[ChatMessage(role="user", content="hi")])
        )

    assert response.content == "Hello there"
    assert response.provider == "openai"
    assert response.usage.input_tokens == 10
    assert response.usage.output_tokens == 3


@pytest.mark.asyncio
@respx.mock
async def test_send_message_raises_provider_error_on_http_error() -> None:
    respx.post(OPENAI_API_URL).mock(return_value=httpx.Response(400, json={"error": "bad request"}))

    async with httpx.AsyncClient() as client:
        provider = OpenAIProvider(api_key="fake-key", client=client)
        with pytest.raises(ProviderError):
            await provider.send_message(
                ChatRequest(model="gpt-4o-mini", messages=[ChatMessage(role="user", content="hi")])
            )


@pytest.mark.asyncio
@respx.mock
async def test_send_message_raises_timeout_error_on_timeout() -> None:
    respx.post(OPENAI_API_URL).mock(side_effect=httpx.TimeoutException("timed out"))

    async with httpx.AsyncClient() as client:
        provider = OpenAIProvider(api_key="fake-key", client=client)
        with pytest.raises(ProviderTimeoutError):
            await provider.send_message(
                ChatRequest(model="gpt-4o-mini", messages=[ChatMessage(role="user", content="hi")])
            )
