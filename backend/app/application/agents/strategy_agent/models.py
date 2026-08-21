from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


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


class StrategyAgentError(Exception):
    def __init__(self, code: StrategyAgentFailureCode, message: str, *, metadata: dict[str, JsonValue] | None = None):
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}
