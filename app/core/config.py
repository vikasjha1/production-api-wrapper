from functools import lru_cache

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

    # Provider credentials — left optional for now (Phase 1 doesn't call
    # any provider). We revisit this in Phase 2 and make them required,
    # with a startup check, once real provider calls depend on them.
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None

    # Redis / Postgres — stubbed now, wired up for real once those
    # phases start. Defaults point at local dev services.
    redis_url: str = "redis://localhost:6379/0"
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/gateway"


@lru_cache
def get_settings() -> Settings:
    return Settings()
