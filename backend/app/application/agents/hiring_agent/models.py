from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from backend.app.application.agents.hiring_agent.pipeline import HiringEvidence, HiringSignal


class HiringAgentStatus(StrEnum):
    ANALYZED = "analyzed"
    INSUFFICIENT_DATA = "insufficient_data"


class HiringAgentFailureCode(StrEnum):
    DISABLED = "disabled_agent"
    INVALID_REQUEST = "invalid_request"
    AUTHENTICATION = "authentication"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


class HiringAgentAppRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str = Field(min_length=1, max_length=200)


class HiringAgentAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: HiringAgentStatus
    organization: str
    generated_at: str
    total_input_jobs: int = Field(ge=0)
    unique_jobs: int = Field(ge=0)
    enriched_jobs: int = Field(ge=0)
    failed_enrichments: int = Field(ge=0)
    hiring_signals: list[HiringSignal]
    evidence: list[HiringEvidence]
    warnings: list[str]
    provider: str
    model: str
    agent_version: str


class HiringAgentError(Exception):
    def __init__(
        self,
        code: HiringAgentFailureCode,
        message: str,
        *,
        metadata: dict[str, JsonValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}
