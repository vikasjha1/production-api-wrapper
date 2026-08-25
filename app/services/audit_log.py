from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RequestLog


async def write_audit_log(
    session: AsyncSession,
    *,
    request_id: str,
    client_id: str,
    provider: str,
    used_provider: str,
    model: str,
    status: str,
    error_code: str | None,
    status_code: int,
    cache_hit: bool,
    fallback_used: bool,
    input_tokens: int | None,
    output_tokens: int | None,
    cost_usd: float | None,
    latency_ms: float,
    prompt_injection_suspected: bool = False,
) -> None:
    entry = RequestLog(
        request_id=request_id,
        client_id=client_id,
        provider=provider,
        used_provider=used_provider,
        model=model,
        status=status,
        error_code=error_code,
        status_code=status_code,
        cache_hit=cache_hit,
        fallback_used=fallback_used,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost_usd=cost_usd,
        latency_ms=latency_ms,
        prompt_injection_suspected=prompt_injection_suspected,
    )
    session.add(entry)
    await session.commit()
