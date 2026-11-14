from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "URL Shortener API"
    environment: str = "development"
    base_url: str = "http://localhost:8000"
    database_url: str = "sqlite:///./data/shortener.db"
    short_code_length: int = Field(default=6, ge=4, le=12)
    max_collision_retries: int = Field(default=5, ge=1, le=20)
    reserved_aliases: set[str] = {"health", "docs", "redoc", "openapi.json", "api"}
    valkey_url: str = "valkey://localhost:6379/0"
    cache_ttl_seconds: int = 3600
    rate_limit_requests: int = 20
    rate_limit_window_seconds: int = 60
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
