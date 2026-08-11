"""Application configuration loaded from environment variables and a local .env file."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly typed runtime settings; secrets are never included in normal logs."""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="ZHQ_", extra="ignore")

    app_name: str = "智汇齐鲁·全域同频"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False
    secret_key: SecretStr = Field(default=SecretStr("development-only-change-me"))
    ai_provider: Literal["deepseek", "offline"] = "deepseek"
    ai_base_url: str = "https://api.deepseek.com"
    ai_model: str = "deepseek-chat"
    ai_api_key: SecretStr | None = None
    ai_connect_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    ai_read_timeout_seconds: float = Field(default=60.0, gt=0, le=300)
    ai_max_context_messages: int = Field(default=12, ge=2, le=30)
    database_url: str | None = None
    redis_url: str | None = None
    memory_backend: Literal["memory", "sqlite"] = "memory"
    sqlite_memory_path: str = "./data/zhihui_qilu_memory.sqlite3"
    web_origin: str = "http://localhost:5173"
    ephemeral_memory_ttl_seconds: int = Field(default=4 * 60 * 60, gt=0)
    short_term_memory_ttl_seconds: int = Field(default=7 * 24 * 60 * 60, gt=0)
    security_rate_limit_per_minute: int = Field(default=60, gt=0)

    @model_validator(mode="after")
    def validate_production_secrets(self) -> "Settings":
        """Reject development defaults whenever the deployment is production."""
        if self.environment == "production":
            if self.secret_key.get_secret_value() == "development-only-change-me":
                raise ValueError("ZHQ_SECRET_KEY must be set to a non-default value in production")
            if self.ai_provider != "offline" and self.ai_api_key is None:
                raise ValueError("ZHQ_AI_API_KEY is required for the configured production AI provider")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide immutable settings instance."""
    return Settings()
