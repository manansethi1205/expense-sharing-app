from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://expense:expense@localhost:5432/expenses"
    exact_settlement_threshold: int = Field(default=16, ge=0, le=16)

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, value: str) -> str:
        # Render supplies a standard PostgreSQL URI, without SQLAlchemy's driver suffix.
        url = make_url(value)
        if url.drivername in {"postgres", "postgresql"}:
            return url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
