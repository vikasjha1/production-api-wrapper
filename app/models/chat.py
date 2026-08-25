from typing import Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1, max_length=50_000)


class ChatFallback(BaseModel):
    provider: str
    model: str = Field(min_length=1, max_length=200)


class ChatRequest(BaseModel):
    model: str = Field(min_length=1, max_length=200)
    messages: list[ChatMessage] = Field(min_length=1, max_length=100)
    max_tokens: int = Field(default=1024, gt=0, le=8192)
    temperature: float = Field(default=1.0, ge=0.0, le=2.0)
    fallback: ChatFallback | None = None


class ChatUsage(BaseModel):
    input_tokens: int
    output_tokens: int


class ChatResponse(BaseModel):
    content: str
    model: str
    provider: str
    usage: ChatUsage
