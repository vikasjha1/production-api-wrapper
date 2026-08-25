from datetime import datetime
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App metadata
    app_name: str = "Production API Wrapper"
    app_version: str = "0.1.0"
    environment: str = "development"  # development | staging | production
    debug: bool = False

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    # API keys allowed to call this gateway: raw key -> client name.
    # Temporary home until a real database exists (see api_keys usage
    # in app/api/deps.py). Set via API_KEYS as a JSON object in .env.
    api_keys: dict[str, str] = Field(default_factory=dict)

    # Optional per-key restrictions, both additive to api_keys above so a
    # key absent from either dict is simply unrestricted / never expires —
    # existing keys and existing tests are unaffected unless explicitly
    # opted in. raw key -> allowed provider names.
    api_key_allowed_providers: dict[str, list[str]] = Field(default_factory=dict)
    # raw key -> expiry timestamp (UTC). Keys not listed never expire.
    api_key_expires_at: dict[str, datetime] = Field(default_factory=dict)

    # Provider credentials — left optional for now (Phase 1 doesn't call
    # any provider). We revisit this in Phase 2 and make them required,
    # with a startup check, once real provider calls depend on them.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Redis / Postgres — stubbed now, wired up for real once those
    # phases start. Defaults point at local dev services.
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/gateway"

    # Rate limiting: max requests per client within the rolling window.
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # How long an identical chat request's response stays cached.
    cache_ttl_seconds: int = 300

    # Retry policy for transient provider failures.
    retry_max_attempts: int = 3
    retry_base_delay_seconds: float = 0.5

    # Circuit breaker: consecutive failures before a provider is considered
    # down, and how long to wait before cautiously testing recovery.
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_recovery_timeout_seconds: float = 30.0

    # Idempotency keys: how long an in-flight request holds its lock before
    # being considered abandoned, and how long a completed result stays
    # available for replay.
    idempotency_lock_ttl_seconds: int = 60
    idempotency_result_ttl_seconds: int = 86400

    # Shared HTTP client tuning for outbound provider calls: connection pool
    # limits and the default request timeout. Defaults match httpx's own
    # built-in defaults, just made explicit and configurable instead of
    # invisible library behavior.
    http_max_connections: int = 100
    http_max_keepalive_connections: int = 20
    http_keepalive_expiry_seconds: float = 5.0
    http_timeout_seconds: float = 30.0

    # How long /v1/ready waits for each dependency check before treating
    # it as unreachable, rather than hanging indefinitely.
    readiness_check_timeout_seconds: float = 2.0

    # Browser origins allowed to call this gateway cross-origin, e.g.
    # ["https://dashboard.example.com"]. Empty by default: this API is
    # authenticated with a raw header (X-API-Key), not cookies, so there's
    # no same-site/CSRF concern — CORS only matters once a specific
    # browser-based frontend needs to call it, so it stays opt-in.
    cors_allowed_origins: list[str] = Field(default_factory=list)


@lru_cache
def get_settings() -> Settings:
    return Settings()
