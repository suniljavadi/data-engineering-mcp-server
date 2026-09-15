from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "sqlite:///data/demo.db"
    log_level: str = "INFO"
    sql_query_timeout_seconds: int = 2
    max_query_rows: int = 100
    max_log_rows: int = 100

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def sqlite_path(self) -> Path:
        return Path(self.database_url.removeprefix("sqlite:///"))


settings = Settings()