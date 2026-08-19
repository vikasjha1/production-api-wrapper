import httpx

from app.core.exceptions import BadRequestError, ProviderError, ProviderTimeoutError
from app.models.chat import ChatRequest, ChatResponse, ChatUsage

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str, client: httpx.AsyncClient) -> None:
        self._api_key = api_key
        self._client = client

    async def send_message(self, request: ChatRequest) -> ChatResponse:
        payload = {
            "model": request.model,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [
                {"role": message.role, "content": message.content} for message in request.messages
            ],
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "content-type": "application/json",
        }

        try:
            response = await self._client.post(OPENAI_API_URL, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("OpenAI request timed out") from exc

        if response.status_code >= 500:
            raise ProviderError(f"OpenAI returned {response.status_code}: {response.text}")
        if response.status_code >= 400:
            raise BadRequestError(
                f"OpenAI rejected the request ({response.status_code}): {response.text}"
            )

        data = response.json()
        choice = data["choices"][0]

        return ChatResponse(
            content=choice["message"]["content"],
            model=data["model"],
            provider=self.name,
            usage=ChatUsage(
                input_tokens=data["usage"]["prompt_tokens"],
                output_tokens=data["usage"]["completion_tokens"],
            ),
        )
