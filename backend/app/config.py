from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HiringSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BSI_", extra="ignore")

    sqlite_database_path: Path = Path("data/hiring-intelligence.sqlite3")
    wells_fargo_request_timeout_seconds: float = Field(default=20.0, gt=0)
    wells_fargo_retry_count: int = Field(default=2, ge=0)
