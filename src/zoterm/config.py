from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    api_base_url: str = Field(default="http://localhost:23119/api")
    request_timeout: float = Field(default=10.0)
    page_size: int = Field(default=100, ge=1, le=500)

    model_config = SettingsConfigDict(
        env_prefix="ZOTERM_",
        env_file=".env",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
