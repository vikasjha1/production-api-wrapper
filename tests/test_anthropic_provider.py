import httpx
import pytest
import respx

from app.core.exceptions import BadRequestError, ProviderError, ProviderTimeoutError
from app.models.chat import ChatMessage, ChatRequest
from app.services.providers.anthropic import ANTHROPIC_API_URL, AnthropicProvider


@pytest.mark.asyncio
@respx.mock
async def test_send_message_parses_successful_response() -> None:
    respx.post(ANTHROPIC_API_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "content": [{"type": "text", "text": "Hello there"}],
                "model": "claude-haiku-4-5-20251001",
                "usage": {"input_tokens": 10, "output_tokens": 3},
            },
        )
    )

    async with httpx.AsyncClient() as client:
        provider = AnthropicProvider(api_key="fake-key", client=client)
        response = await provider.send_message(
            ChatRequest(
                model="claude-haiku-4-5-20251001",
                messages=[ChatMessage(role="user", content="hi")],
            )
        )

    assert response.content == "Hello there"
    assert response.provider == "anthropic"
    assert response.usage.input_tokens == 10
    assert response.usage.output_tokens == 3


@pytest.mark.asyncio
@respx.mock
async def test_send_message_raises_bad_request_error_on_4xx() -> None:
    respx.post(ANTHROPIC_API_URL).mock(
        return_value=httpx.Response(400, json={"error": "bad request"})
    )

    async with httpx.AsyncClient() as client:
        provider = AnthropicProvider(api_key="fake-key", client=client)
        with pytest.raises(BadRequestError):
            await provider.send_message(
                ChatRequest(
                    model="claude-haiku-4-5-20251001",
                    messages=[ChatMessage(role="user", content="hi")],
                )
            )


@pytest.mark.asyncio
@respx.mock
async def test_send_message_raises_provider_error_on_5xx() -> None:
    respx.post(ANTHROPIC_API_URL).mock(
        return_value=httpx.Response(503, json={"error": "overloaded"})
    )

    async with httpx.AsyncClient() as client:
        provider = AnthropicProvider(api_key="fake-key", client=client)
        with pytest.raises(ProviderError):
            await provider.send_message(
                ChatRequest(
                    model="claude-haiku-4-5-20251001",
                    messages=[ChatMessage(role="user", content="hi")],
                )
            )


@pytest.mark.asyncio
@respx.mock
async def test_send_message_raises_timeout_error_on_timeout() -> None:
    respx.post(ANTHROPIC_API_URL).mock(side_effect=httpx.TimeoutException("timed out"))

    async with httpx.AsyncClient() as client:
        provider = AnthropicProvider(api_key="fake-key", client=client)
        with pytest.raises(ProviderTimeoutError):
            await provider.send_message(
                ChatRequest(
                    model="claude-haiku-4-5-20251001",
                    messages=[ChatMessage(role="user", content="hi")],
                )
            )
