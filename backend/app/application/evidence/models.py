from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, JsonValue

from backend.app.application.hiring import EnrichmentSeniority
from backend.app.application.technology import TechnologyCategory
from backend.app.domain.intelligence import SourceType


class EvidenceSignalReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    signal_id: UUID
    signal_type: str
    title: str


class EvidenceTechnologyObservationReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    technology: str
    category: TechnologyCategory
    confidence: float = Field(ge=0, le=1)
    support_excerpt: str | None = None


class UnifiedEvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID
    organization: str
    source: str
    source_type: SourceType
    source_url: HttpUrl
    captured_at: datetime
    observed_at: date
    job_id: UUID
    job_title: str
    job_location: str
    business_unit: str | None = None
    enrichment_present: bool
    enrichment_provider: str | None = None
    enrichment_model: str | None = None
    enrichment_schema_version: str | None = None
    application_confidence: float | None = Field(default=None, ge=0, le=1)
    technologies: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    seniority: EnrichmentSeniority | None = None
    related_hiring_signals: list[EvidenceSignalReference] = Field(default_factory=list)
    related_technology_observation_count: int = Field(ge=0)
    related_technology_signals: list[EvidenceSignalReference] = Field(default_factory=list)
    evidence_preview: str | None = None


class UnifiedEvidenceDetail(UnifiedEvidenceRecord):
    source_excerpt: str | None = None
    raw_reference: str | None = None
    collector_identity: str
    provenance_metadata: dict[str, JsonValue] = Field(default_factory=dict)
    enrichment_limitations: list[str] = Field(default_factory=list)
    technology_observations: list[EvidenceTechnologyObservationReference] = Field(default_factory=list)


class EvidenceSourceDistribution(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    source_type: SourceType
    evidence_count: int = Field(ge=0)


class EvidenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    total_evidence_records: int = Field(ge=0)
    total_jobs: int = Field(ge=0)
    jobs_with_evidence: int = Field(ge=0)
    evidence_coverage: float = Field(ge=0, le=100)
    enriched_evidence_count: int = Field(ge=0)
    enrichment_coverage: float = Field(ge=0, le=100)
    evidence_supporting_hiring_signals: int = Field(ge=0)
    evidence_supporting_technology_observations: int = Field(ge=0)
    evidence_supporting_technology_signals: int = Field(ge=0)
    source_distribution: list[EvidenceSourceDistribution]
    observation_start: date | None = None
    observation_end: date | None = None
    generated_at: datetime


class EvidenceRecordFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search: str | None = None
    source: str | None = None
    enriched: bool | None = None
    technology: str | None = None
    capability: str | None = None
    location: str | None = None
    job_id: UUID | None = None
    limit: int = Field(default=25, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class UnifiedEvidencePage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[UnifiedEvidenceRecord]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    returned_count: int = Field(ge=0)
