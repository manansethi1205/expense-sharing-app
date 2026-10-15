from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://expense:expense@localhost:5432/expenses"
    exact_settlement_threshold: int = Field(default=16, ge=0, le=16)


@lru_cache
def get_settings() -> Settings:
    return Settings()
