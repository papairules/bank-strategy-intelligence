from pathlib import Path

from pydantic import Field, field_validator
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
    evidence_agent_enabled: bool = False
    evidence_agent_provider: str = "vertex_gemini"
    evidence_agent_model: str = "gemini-2.5-flash"
    evidence_agent_max_tool_calls: int = Field(default=3, ge=1, le=5)
    evidence_agent_max_evidence: int = Field(default=10, ge=1, le=20)
    strategy_agent_enabled: bool = False
    strategy_agent_provider: str = "vertex_gemini"
    strategy_agent_model: str = "gemini-2.5-flash"
    strategy_agent_max_tool_calls: int = Field(default=6, ge=1, le=10)
    strategy_agent_max_search_results: int = Field(default=10, ge=1, le=50)
    strategy_agent_max_evidence: int = Field(default=10, ge=1, le=20)
    strategy_agent_max_payload_chars: int = Field(default=100_000, ge=1_000)
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
        ]
    )

    @field_validator("cors_origins")
    @classmethod
    def reject_wildcard_cors_with_credentials(cls, value: list[str]) -> list[str]:
        if "*" in value:
            raise ValueError("cors_origins must not contain a wildcard")
        return value
