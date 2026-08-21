from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.application.agents.evidence_agent import (
    EvidenceAgentCitation,
    EvidenceAgentStatus,
)


class EvidenceAgentAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def reject_blank_question(self):
        if not self.question.strip():
            raise ValueError("question must contain non-whitespace text")
        return self


class EvidenceAgentCitationResponse(EvidenceAgentCitation):
    model_config = ConfigDict(extra="forbid")


class EvidenceAgentAnswerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: EvidenceAgentStatus
    organization: str
    question: str
    answer: str
    citations: list[EvidenceAgentCitationResponse]
    evidence_records_considered: int = Field(ge=0)
    tool_calls_used: int = Field(ge=0)
    reliability: float = Field(ge=0, le=1)
    limitations: list[str]
    provider: str
    model: str
    agent_version: str


class EvidenceAgentErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
