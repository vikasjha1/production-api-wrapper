from redis.asyncio import Redis

from app.core.exceptions import ConflictError
from app.models.chat import ChatResponse

_IN_PROGRESS = b"IN_PROGRESS"


def _build_key(client_id: str, idempotency_key: str) -> str:
    return f"idempotency:{client_id}:{idempotency_key}"


async def claim_idempotency_key(
    redis: Redis, client_id: str, idempotency_key: str, lock_ttl_seconds: int
) -> ChatResponse | None:
    key = _build_key(client_id, idempotency_key)

    claimed = await redis.set(key, _IN_PROGRESS, nx=True, ex=lock_ttl_seconds)
    if claimed:
        return None

    existing = await redis.get(key)
    if existing is None:
        # Lock expired between our SET NX and this GET — treat as if it
        # never existed and let the caller proceed with a fresh attempt.
        return None

    if existing == _IN_PROGRESS:
        raise ConflictError("A request with this idempotency key is already in progress")

    return ChatResponse.model_validate_json(existing)


async def store_idempotent_response(
    redis: Redis,
    client_id: str,
    idempotency_key: str,
    response: ChatResponse,
    ttl_seconds: int,
) -> None:
    key = _build_key(client_id, idempotency_key)
    await redis.set(key, response.model_dump_json(), ex=ttl_seconds)


async def release_idempotency_key(redis: Redis, client_id: str, idempotency_key: str) -> None:
    key = _build_key(client_id, idempotency_key)
    await redis.delete(key)
