import httpx

from app.core.exceptions import BadRequestError, ProviderError, ProviderTimeoutError
from app.models.chat import ChatRequest, ChatResponse, ChatUsage

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._client = client

    async def send_message(self, request: ChatRequest) -> ChatResponse:
        conversation = [
            {"role": message.role, "content": message.content}
            for message in request.messages
            if message.role != "system"
        ]
        system_prompt = "\n".join(
            message.content for message in request.messages if message.role == "system"
        )

        payload: dict[str, object] = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": conversation,
        }
        if system_prompt:
            payload["system"] = system_prompt

        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

        try:
            response = await self._client.post(
                ANTHROPIC_API_URL, json=payload, headers=headers, timeout=30.0
            )
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("Anthropic request timed out") from exc

        if response.status_code >= 500:
            raise ProviderError(f"Anthropic returned {response.status_code}: {response.text}")
        if response.status_code >= 400:
            raise BadRequestError(
                f"Anthropic rejected the request ({response.status_code}): {response.text}"
            )

        data = response.json()
        text = "".join(block["text"] for block in data["content"] if block["type"] == "text")

        return ChatResponse(
            content=text,
            model=data["model"],
            provider=self.name,
            usage=ChatUsage(
                input_tokens=data["usage"]["input_tokens"],
                output_tokens=data["usage"]["output_tokens"],
            ),
        )
