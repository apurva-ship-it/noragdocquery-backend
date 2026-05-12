from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./noragdocquery.db"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    openrouter_model: str = "openai/gpt-4o-mini"
    max_file_size_mb: int = 10
    chunk_size: int = 1000
    max_context_tokens: int = 8000


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
