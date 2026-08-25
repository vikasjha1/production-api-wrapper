import datetime

from sqlalchemy import DateTime, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RequestLog(Base):
    __tablename__ = "request_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(index=True)
    client_id: Mapped[str] = mapped_column(index=True)
    provider: Mapped[str]
    used_provider: Mapped[str]
    model: Mapped[str]
    status: Mapped[str]
    error_code: Mapped[str | None]
    status_code: Mapped[int]
    cache_hit: Mapped[bool]
    fallback_used: Mapped[bool]
    prompt_injection_suspected: Mapped[bool] = mapped_column(default=False, server_default=false())
    input_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    cost_usd: Mapped[float | None]
    latency_ms: Mapped[float]
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
