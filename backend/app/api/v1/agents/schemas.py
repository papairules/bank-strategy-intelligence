from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.app.application.agents.evidence_agent import (
    EvidenceAgentCitation,
    EvidenceAgentStatus,
)
from backend.app.application.agents.hiring_agent import (
    HiringAgentStatus,
    HiringEvidence,
    HiringSignal,
)
from backend.app.application.agents.strategy_agent import (
    StrategyAgentStatus,
    StrategySupportClass,
    StrategicSignal,
)
from backend.app.application.agents.supervisor_agent import (
    ReportQuestionAnswer,
    ReportQuestionRequest,
    SupervisorReportResult,
)
from uuid import UUID


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


class StrategyAgentAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=2000)
    time_horizon: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def reject_blank_question(self):
        if not self.question.strip():
            raise ValueError("question must contain non-whitespace text")
        return self


class StrategySupportReferenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reference: str
    domain: str
    support_class: StrategySupportClass
    tool_name: str
    evidence_ids: list[UUID]
    job_ids: list[UUID]
    signal_ids: list[UUID]


class StrategyFindingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    statement: str
    support: list[StrategySupportReferenceResponse]


class StrategyAgentAnswerResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: StrategyAgentStatus
    organization: str
    question: str
    executive_summary: str
    findings: list[StrategyFindingResponse]
    reliability: float = Field(ge=0, le=1)
    limitations: list[str]
    tool_calls_used: int = Field(ge=0)
    provider: str
    model: str
    agent_version: str
    strategic_signals: list[StrategicSignal] = Field(default_factory=list)


class HiringAgentAnswerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def reject_blank_organization(self):
        if not self.organization.strip():
            raise ValueError("organization must contain non-whitespace text")
        return self


class HiringAgentAnswerResponse(BaseModel):
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


class SupervisorReportApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str = Field(min_length=1, max_length=200)
    question: str | None = Field(default=None, min_length=1, max_length=2000)
    time_horizon: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def reject_blank_values(self):
        if not self.organization.strip():
            raise ValueError("organization must contain non-whitespace text")
        if self.question is not None and not self.question.strip():
            raise ValueError("question must contain non-whitespace text")
        return self


class SupervisorReportApiResponse(SupervisorReportResult):
    model_config = ConfigDict(extra="forbid")


class ReportQuestionApiRequest(ReportQuestionRequest):
    model_config = ConfigDict(extra="forbid")


class ReportQuestionApiResponse(ReportQuestionAnswer):
    model_config = ConfigDict(extra="forbid")
