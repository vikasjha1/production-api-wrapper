from typing import Protocol

from app.models.chat import ChatRequest, ChatResponse


class Provider(Protocol):
    name: str

    async def send_message(self, request: ChatRequest) -> ChatResponse: ...
