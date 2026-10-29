from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///data/demo.db"
    log_level: str = "INFO"
    sql_query_timeout_seconds: int = Field(default=2, ge=1, le=300)
    max_query_rows: int = Field(default=100, ge=1, le=100)
    max_log_rows: int = Field(default=100, ge=1, le=100)

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator("database_url")
    @classmethod
    def require_sqlite_url(cls, value: str) -> str:
        if not value.startswith("sqlite:///"):
            raise ValueError("DATABASE_URL must be a SQLite file URL")
        path = value.removeprefix("sqlite:///")
        if not path or path == ":memory:":
            raise ValueError("DATABASE_URL must point to a persistent SQLite file")
        return value

    @field_validator("log_level", mode="before")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = str(value).upper()
        if normalized not in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
            raise ValueError("LOG_LEVEL must be CRITICAL, ERROR, WARNING, INFO, or DEBUG")
        return normalized

    @property
    def sqlite_path(self) -> Path:
        return Path(self.database_url.removeprefix("sqlite:///"))


settings = Settings()