from pydantic import BaseModel


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatFallback(BaseModel):
    provider: str
    model: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    max_tokens: int = 1024
    temperature: float = 1.0
    fallback: ChatFallback | None = None


class ChatUsage(BaseModel):
    input_tokens: int
    output_tokens: int


class ChatResponse(BaseModel):
    content: str
    model: str
    provider: str
    usage: ChatUsage
