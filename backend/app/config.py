from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HiringSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BSI_", extra="ignore")

    sqlite_database_path: Path = Path("data/hiring-intelligence.sqlite3")
    wells_fargo_request_timeout_seconds: float = Field(default=20.0, gt=0)
    wells_fargo_retry_count: int = Field(default=2, ge=0)
    wells_fargo_schedule_enabled: bool = False
    wells_fargo_schedule_interval_seconds: int = Field(default=86_400, ge=60)
    wells_fargo_schedule_max_pages: int = Field(default=1, ge=1)
    wells_fargo_schedule_max_records: int = Field(default=20, ge=1)
    hiring_enrichment_enabled: bool = False
    hiring_llm_provider: str = "vertex_gemini"
    gcp_project: str | None = None
    gcp_location: str = "global"
    gemini_model: str = "gemini-2.5-flash"
    gemini_temperature: float = Field(default=0.1, ge=0, le=2)
    gemini_max_output_tokens: int = Field(default=4096, ge=1)
