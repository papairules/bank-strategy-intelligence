from enum import StrEnum
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator


SourceType = Literal[
    "earnings_release", "annual_report", "quarterly_report", "sec_filing",
    "investor_presentation", "earnings_call", "company_announcement",
    "company_strategy_page", "leadership_statement", "news",
    "industry_research", "other",
]

SignalType = Literal[
    "GROWTH", "INVESTMENT", "REVENUE_GROWTH", "CAPITAL_ALLOCATION",
    "NEW_PRODUCT", "MARKET_EXPANSION", "PARTNERSHIP", "ACQUISITION",
    "TECHNOLOGY_ADOPTION", "TRANSFORMATION", "COST_REDUCTION",
    "REGULATORY_PRIORITY", "GUIDANCE",
]

StrategicDirection = Literal[
    "grow", "increase_investment", "transform", "optimize", "reduce",
    "exit", "maintain", "reallocate",
]


def _validated_publication_date(value: str | None) -> str | None:
    if value is None:
        return None
    candidate = value.strip()
    if len(candidate) != 10:
        return None
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return None


class StrategyAgentStatus(StrEnum):
    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class StrategySupportClass(StrEnum):
    SOURCE_EVIDENCE = "source_evidence"
    AI_ENRICHMENT = "ai_enrichment"
    DERIVED_ANALYTICS = "derived_analytics"
    DERIVED_SIGNAL = "derived_signal"


class StrategyAgentFailureCode(StrEnum):
    DISABLED = "disabled_agent"
    INVALID_REQUEST = "invalid_request"
    ORGANIZATION_SCOPE_MISMATCH = "organization_scope_mismatch"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    AUTHENTICATION = "authentication"
    PERMISSIONS = "permissions"
    QUOTA = "quota"
    TIMEOUT = "timeout"
    INVALID_PROVIDER_REQUEST = "invalid_provider_request"
    MALFORMED_PROVIDER_OUTPUT = "malformed_provider_output"
    INVALID_TOOL_REQUEST = "invalid_tool_request"
    TOOL_EXECUTION_LIMIT = "tool_execution_limit"
    TOOL_EXECUTION_FAILURE = "tool_execution_failure"
    PAYLOAD_LIMIT = "payload_limit"
    REFERENCE_VALIDATION = "reference_validation"
    CLAIM_VALIDATION = "claim_validation"
    PROVENANCE_VALIDATION = "provenance_validation"


class StrategyAgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=2000)
    time_horizon: str | None = Field(default=None, min_length=1, max_length=100)

    @model_validator(mode="after")
    def reject_blank(self):
        if not self.question.strip():
            raise ValueError("question must contain non-whitespace text")
        return self


class StrategyToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    input_schema: dict[str, JsonValue]


class StrategyToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    call_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class StrategyToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    call_id: str
    name: str
    result: dict[str, JsonValue]


class StrategySupportReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reference: str
    domain: str
    support_class: StrategySupportClass
    tool_name: str
    evidence_ids: list[UUID] = Field(default_factory=list)
    job_ids: list[UUID] = Field(default_factory=list)
    signal_ids: list[UUID] = Field(default_factory=list)


class StrategyProviderFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1, max_length=2000)
    citation_references: list[str] = Field(min_length=1, max_length=10)


class StrategyProviderOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    executive_summary: str = Field(min_length=1, max_length=4000)
    findings: list[StrategyProviderFinding] = Field(default_factory=list, max_length=8)
    limitations: list[str] = Field(default_factory=list, max_length=10)


class StrategyProviderStage(StrEnum):
    PLAN = "plan"
    ANSWER = "answer"


class StrategyProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: StrategyProviderStage
    system_policy: str
    request: StrategyAgentRequest
    allowed_tools: list[StrategyToolSpec]
    tool_results: list[StrategyToolResult] = Field(default_factory=list)
    support_references: list[StrategySupportReference] = Field(default_factory=list)


class StrategyProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_calls: list[StrategyToolCall] = Field(default_factory=list)
    output: StrategyProviderOutput | None = None
    provider: str
    model: str
    agent_version: str


class StrategyFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    statement: str
    support: list[StrategySupportReference]


class StrategyAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: StrategyAgentStatus
    organization: str
    question: str
    executive_summary: str
    findings: list[StrategyFinding]
    reliability: float = Field(ge=0, le=1)
    limitations: list[str]
    tool_calls_used: int = Field(ge=0)
    provider: str
    model: str
    agent_version: str
    strategic_signals: list["StrategicSignal"] = Field(default_factory=list)


class StrategyAgentError(Exception):
    def __init__(self, code: StrategyAgentFailureCode, message: str, *, metadata: dict[str, JsonValue] | None = None):
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}


class StrategyAgentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    company: str = Field(min_length=1)
    question: str = Field(min_length=1)
    time_horizon: str | None = None


class ResearchPlan(BaseModel):
    queries: list[str] = Field(min_length=5, max_length=8)


class Source(BaseModel):
    source_id: str = ""
    title: str
    url: str
    publisher: str | None = None
    source_type: SourceType = "other"
    publication_date: str | None = None
    content: str

    @field_validator("publication_date", mode="before")
    @classmethod
    def validate_publication_date(cls, value: object) -> str | None:
        return _validated_publication_date(value if isinstance(value, str) else None)


class SearchResults(BaseModel):
    results: list[Source] = Field(default_factory=list)


class Evidence(BaseModel):
    evidence_id: str = ""
    theme: str
    business_unit: str | None = None
    signal_type: SignalType
    direction: str | None = None
    statement: str
    time_horizon: str | None = None
    source_id: str
    source_url: str
    source_type: SourceType
    publication_date: str | None = None

    @field_validator("publication_date", mode="before")
    @classmethod
    def validate_publication_date(cls, value: object) -> str | None:
        return _validated_publication_date(value if isinstance(value, str) else None)


class EvidenceBatch(BaseModel):
    evidence: list[Evidence] = Field(default_factory=list)


class StrategicSignalDraft(BaseModel):
    priority: str
    business_unit: str | None = None
    direction: StrategicDirection
    time_horizon: str | None = None
    hypothesis: str
    supporting_evidence_ids: list[str]


class StrategicSignalDrafts(BaseModel):
    signals: list[StrategicSignalDraft] = Field(default_factory=list)


class StrategicSignal(StrategicSignalDraft):
    confidence: float = Field(ge=0, le=1)
    confidence_breakdown: dict[str, float]
    evidence: list[Evidence]


class StrategyAgentOutput(BaseModel):
    company: str
    question: str
    time_horizon: str | None = None
    strategic_signals: list[StrategicSignal] = Field(default_factory=list)
    message: str | None = None


StrategyAgentResult.model_rebuild()
