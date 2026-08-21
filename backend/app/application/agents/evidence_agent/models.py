from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator


class EvidenceAgentStatus(StrEnum):
    ANSWERED = "answered"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class EvidenceRelationshipType(StrEnum):
    SOURCE_EVIDENCE = "source_evidence"
    HIRING_ENRICHMENT = "hiring_enrichment"
    HIRING_SIGNAL = "hiring_signal"
    TECHNOLOGY_OBSERVATION = "technology_observation"
    TECHNOLOGY_SIGNAL = "technology_signal"
    CROSS_DOMAIN_SIGNAL = "cross_domain_signal"


class EvidenceAgentFailureCode(StrEnum):
    DISABLED = "disabled_agent"
    INVALID_REQUEST = "invalid_request"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    AUTHENTICATION = "authentication"
    PERMISSIONS = "permissions"
    QUOTA = "quota"
    TIMEOUT = "timeout"
    MALFORMED_PROVIDER_OUTPUT = "malformed_provider_output"
    INVALID_PROVIDER_REQUEST = "invalid_provider_request"
    INVALID_TOOL_REQUEST = "invalid_tool_request"
    TOOL_EXECUTION_LIMIT = "tool_execution_limit"
    CITATION_VALIDATION = "citation_validation"
    PROVENANCE_VALIDATION = "provenance_validation"


class EvidenceAgentSearchConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    search: str | None = Field(default=None, max_length=200)
    source: str | None = Field(default=None, max_length=100)
    enriched: bool | None = None
    technology: str | None = Field(default=None, max_length=100)
    capability: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=100)


class EvidenceAgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=2000)
    job_id: UUID | None = None
    evidence_id: UUID | None = None
    search_constraints: EvidenceAgentSearchConstraints | None = None
    maximum_evidence_records: int = Field(default=10, ge=1, le=20)

    @model_validator(mode="after")
    def reject_blank_question(self):
        if not self.question.strip():
            raise ValueError("question must contain non-whitespace text")
        return self


class EvidenceAgentToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    call_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, JsonValue] = Field(default_factory=dict)


class EvidenceAgentToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    call_id: str
    name: str
    result: dict[str, JsonValue]


class EvidenceAgentCitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: UUID
    job_id: UUID
    relationship_type: EvidenceRelationshipType
    excerpt: str | None = Field(default=None, max_length=500)
    source_type: str | None = Field(default=None, max_length=100)


class EvidenceAgentAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: EvidenceAgentStatus
    answer: str = Field(min_length=1, max_length=5000)
    citations: list[EvidenceAgentCitation] = Field(default_factory=list, max_length=20)
    limitations: list[str] = Field(default_factory=list, max_length=10)
    model_confidence: float | None = Field(default=None, ge=0, le=1)


class EvidenceAgentProviderStage(StrEnum):
    PLAN = "plan"
    ANSWER = "answer"


class EvidenceAgentToolSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    description: str
    input_schema: dict[str, JsonValue]


class EvidenceAgentProviderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stage: EvidenceAgentProviderStage
    system_policy: str
    request: EvidenceAgentRequest
    allowed_tools: list[EvidenceAgentToolSpec]
    tool_results: list[EvidenceAgentToolResult] = Field(default_factory=list)


class EvidenceAgentProviderResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool_calls: list[EvidenceAgentToolCall] = Field(default_factory=list)
    answer: EvidenceAgentAnswer | None = None
    provider: str
    model: str
    agent_version: str


class EvidenceAgentResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: EvidenceAgentStatus
    organization: str
    question: str
    answer: str
    citations: list[EvidenceAgentCitation]
    evidence_records_considered: int = Field(ge=0)
    tool_calls_used: int = Field(ge=0)
    reliability: float = Field(ge=0, le=1)
    limitations: list[str]
    provider: str
    model: str
    agent_version: str


class EvidenceAgentError(Exception):
    def __init__(self, code: EvidenceAgentFailureCode, message: str, *, metadata: dict[str, JsonValue] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}
