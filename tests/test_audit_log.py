import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models import RequestLog
from app.services.audit_log import write_audit_log


@pytest_asyncio.fixture
async def session_factory(tmp_path):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}")

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False)
    yield factory

    await engine.dispose()


@pytest.mark.asyncio
async def test_write_audit_log_persists_a_row(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await write_audit_log(
            session,
            request_id="req-1",
            client_id="client-a",
            provider="anthropic",
            used_provider="anthropic",
            model="claude-haiku-4-5-20251001",
            status="success",
            error_code=None,
            status_code=200,
            cache_hit=False,
            fallback_used=False,
            input_tokens=10,
            output_tokens=3,
            cost_usd=0.00004,
            latency_ms=123.4,
        )

    async with session_factory() as session:
        result = await session.execute(select(RequestLog))
        rows = result.scalars().all()

    assert len(rows) == 1
    row = rows[0]
    assert row.request_id == "req-1"
    assert row.client_id == "client-a"
    assert row.status == "success"
    assert row.cost_usd == pytest.approx(0.00004)


@pytest.mark.asyncio
async def test_write_audit_log_stores_error_details(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await write_audit_log(
            session,
            request_id="req-2",
            client_id="client-a",
            provider="anthropic",
            used_provider="anthropic",
            model="claude-haiku-4-5-20251001",
            status="error",
            error_code="provider_error",
            status_code=502,
            cache_hit=False,
            fallback_used=False,
            input_tokens=None,
            output_tokens=None,
            cost_usd=None,
            latency_ms=50.0,
        )

    async with session_factory() as session:
        result = await session.execute(select(RequestLog).where(RequestLog.request_id == "req-2"))
        row = result.scalar_one()

    assert row.status == "error"
    assert row.error_code == "provider_error"
    assert row.input_tokens is None
