from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from backend.app.application.evidence import EvidenceSignalReference, UnifiedEvidenceDetail
from backend.app.application.hiring import (
    CollectionRun,
    EnrichmentSeniority,
    HiringCapability,
    HiringTheme,
)
from backend.app.application.strategy import StrategicCoverageContext
from backend.app.application.technology import (
    TechnologyAnalyticsResult,
    TechnologyCategory,
    TechnologyObservation,
)
from backend.app.domain.hiring import EmploymentType, SeniorityLevel


class AgentToolDomain(StrEnum):
    HIRING = "hiring"
    TECHNOLOGY = "technology"
    EVIDENCE = "evidence"
    STRATEGY = "strategy"


class OrganizationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization: str = Field(min_length=1)


class JobIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID


class EvidenceIdInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: UUID


class JobSearchInput(OrganizationInput):
    location: str | None = None
    capability: str | None = None
    seniority: SeniorityLevel | None = None
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0)


class TechnologyObservationSearchInput(OrganizationInput):
    technology: str | None = None
    category: TechnologyCategory | None = None
    business_unit: str | None = None
    location: str | None = None
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0)


class EvidenceSearchInput(OrganizationInput):
    search: str | None = None
    source: str | None = None
    enriched: bool | None = None
    technology: str | None = None
    capability: str | None = None
    location: str | None = None
    job_id: UUID | None = None
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0)


class CollectionContextInput(OrganizationInput):
    limit: int = Field(default=10, ge=1, le=50)


class AgentJobSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_id: UUID
    evidence_id: UUID
    organization: str
    title: str
    location: str
    country: str
    business_unit: str | None
    capability_classifications: list[str]
    seniority_level: SeniorityLevel | None
    posted_date: date
    employment_type: EmploymentType | None
    source_url: HttpUrl


class AgentEnrichmentSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    available: bool
    provider: str | None = None
    model: str | None = None
    prompt_schema_version: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    capabilities: list[HiringCapability] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    seniority: EnrichmentSeniority | None = None
    business_unit: str | None = None
    themes: list[HiringTheme] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class AgentJobIntelligence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    found: bool
    job: AgentJobSummary | None = None
    enrichment: AgentEnrichmentSummary


class AgentJobSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization: str
    items: list[AgentJobSummary]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class AgentCollectionContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization: str
    runs: list[CollectionRun]
    returned_count: int = Field(ge=0)
    latest_status: str | None = None
    limitations: list[str] = Field(default_factory=list)


class AgentTechnologySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization: str
    total_jobs: int = Field(ge=0)
    enriched_jobs: int = Field(ge=0)
    technology_observation_count: int = Field(ge=0)
    unique_technologies: int = Field(ge=0)
    technology_coverage: float = Field(ge=0, le=1)
    observation_start: date | None = None
    observation_end: date | None = None
    limitations: list[str] = Field(default_factory=list)


class AgentTechnologyAnalytics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analytics: TechnologyAnalyticsResult
    limitations: list[str] = Field(default_factory=list)


class AgentTechnologyObservationSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization: str
    items: list[TechnologyObservation]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)


class EvidenceTrace(BaseModel):
    model_config = ConfigDict(extra="forbid")
    found: bool
    evidence_id: UUID
    job_id: UUID | None = None
    organization: str | None = None
    enrichment_present: bool = False
    enrichment_provider: str | None = None
    enrichment_model: str | None = None
    enrichment_schema_version: str | None = None
    hiring_signals: list[EvidenceSignalReference] = Field(default_factory=list)
    technology_observations: list[str] = Field(default_factory=list)
    technology_signals: list[EvidenceSignalReference] = Field(default_factory=list)
    cross_domain_signal_ids: list[UUID] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class AgentEvidenceDetailResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    found: bool
    detail: UnifiedEvidenceDetail | None = None


class AgentStrategyContext(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization: str
    generated_at: datetime
    observation_start: date | None = None
    observation_end: date | None = None
    hiring_coverage: float = Field(ge=0, le=1)
    enrichment_coverage: float = Field(ge=0, le=1)
    evidence_coverage: float = Field(ge=0, le=1)
    hiring_signal_count: int = Field(ge=0)
    technology_observation_count: int = Field(ge=0)
    technology_signal_count: int = Field(ge=0)
    cross_domain_signal_count: int = Field(ge=0)
    limitations: list[str] = Field(default_factory=list)
    coverage_context: StrategicCoverageContext
