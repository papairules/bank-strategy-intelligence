from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue

from backend.app.application.hiring import (
    CapabilityHiringConcentration,
    CollectionRun,
    EnrichmentField,
    EnrichmentFieldSupport,
    EnrichmentModelMetadata,
    EnrichmentSeniority,
    GeneratedHiringSignal,
    GeographicHiringConcentration,
    HiringCapability,
    HiringSnapshot,
    HiringTheme,
    HiringTrendSummary,
    SeniorityHiringSummary,
)
from backend.app.domain.hiring import EmploymentType, SeniorityLevel
from backend.app.domain.intelligence import SourceType


class JobPostingResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    job_id: UUID
    organization: str
    source_job_id: str
    title: str
    description: str
    location: str
    country: str
    business_unit: str | None
    capability_classifications: list[str]
    skills: list[str]
    technologies: list[str]
    seniority_level: SeniorityLevel | None
    is_leadership: bool
    posted_date: date
    closing_date: date | None
    employment_type: EmploymentType | None
    source_url: HttpUrl
    evidence_id: UUID


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    evidence_id: UUID
    source_url: HttpUrl
    source_type: SourceType
    source_title: str | None
    retrieved_at: datetime
    source_excerpt: str | None
    raw_reference: str | None
    collector_identity: str
    provenance_metadata: dict[str, JsonValue]


class EnrichmentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    job_id: UUID
    evidence_id: UUID
    capability_classifications: list[HiringCapability]
    skills: list[str]
    technologies: list[str]
    seniority_level: EnrichmentSeniority
    is_leadership: bool
    business_unit: str | None
    hiring_themes: list[HiringTheme]
    confidence: float = Field(ge=0, le=1)
    field_confidences: dict[EnrichmentField, float]
    field_support: list[EnrichmentFieldSupport]
    limitations: list[str]
    model_metadata: EnrichmentModelMetadata


class JobPostingListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[JobPostingResponse]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    returned_count: int = Field(ge=0)


class JobDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job: JobPostingResponse
    evidence: EvidenceResponse
    enrichment: EnrichmentResponse | None


class EnrichmentHistoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[EnrichmentResponse]
    returned_count: int = Field(ge=0)


class HiringAnalyticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: HiringSnapshot
    geographic: GeographicHiringConcentration
    capability: CapabilityHiringConcentration
    seniority: SeniorityHiringSummary
    daily_trend: HiringTrendSummary
    weekly_trend: HiringTrendSummary


class HiringSignalsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    generated_at: datetime
    items: list[GeneratedHiringSignal]
    returned_count: int = Field(ge=0)


class OrganizationSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    total_observed_jobs: int
    jobs_with_evidence: int
    evidence_coverage: float
    observation_start: date | None
    observation_end: date | None
    latest_collection_run: CollectionRun | None
    enriched_job_count: int
    enrichment_coverage: float
    signal_count: int
    generated_at: datetime
    geographic: GeographicHiringConcentration
    capability: CapabilityHiringConcentration
    seniority: SeniorityHiringSummary
    trend: HiringTrendSummary


class CollectionRunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CollectionRun]
    limit: int = Field(ge=1)
    returned_count: int = Field(ge=0)
