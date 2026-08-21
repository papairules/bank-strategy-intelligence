from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrategicSignalType(StrEnum):
    CAPABILITY_TECHNOLOGY_ALIGNMENT = "capability_technology_alignment"
    GEOGRAPHIC_TECHNOLOGY_ALIGNMENT = "geographic_technology_alignment"
    BUSINESS_UNIT_TECHNOLOGY_ALIGNMENT = "business_unit_technology_alignment"
    LEADERSHIP_TECHNOLOGY_ALIGNMENT = "leadership_technology_alignment"
    HIRING_TECHNOLOGY_CLUSTER = "hiring_technology_cluster"


class IntelligenceDomain(StrEnum):
    HIRING = "hiring_intelligence"
    TECHNOLOGY = "technology_intelligence"


class StrategicSignalThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    minimum_total_jobs: int = Field(default=10, ge=1)
    minimum_enriched_jobs: int = Field(default=5, ge=1)
    minimum_enrichment_coverage: float = Field(default=0.25, ge=0, le=1)
    minimum_hiring_contributors: int = Field(default=3, ge=1)
    minimum_technology_contributors: int = Field(default=3, ge=1)
    minimum_unique_cross_domain_contributors: int = Field(default=3, ge=1)
    minimum_domain_concentration: float = Field(default=0.3, ge=0, le=1)
    minimum_observation_days: int = Field(default=14, ge=1)
    single_source_data: bool = True
    configuration_version: str = "cross-domain-signals-v1"


class StrategicCoverageContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    total_jobs: int = Field(ge=0)
    jobs_with_evidence: int = Field(ge=0)
    hiring_evidence_coverage: float = Field(ge=0, le=1)
    enriched_jobs: int = Field(ge=0)
    enrichment_coverage: float = Field(ge=0, le=1)
    hiring_signal_count: int = Field(ge=0)
    technology_observation_count: int = Field(ge=0)
    technology_signal_count: int = Field(ge=0)
    observation_start: date | None = None
    observation_end: date | None = None


class StrategicSignalProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    generator: str = "CrossDomainStrategicSignalService"
    configuration_version: str
    deterministic: bool = True


class CrossDomainStrategicSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: UUID
    organization: str
    signal_type: StrategicSignalType
    title: str
    summary: str
    primary_subject: str
    related_subjects: list[str]
    domains_involved: list[IntelligenceDomain]
    observation_start: date
    observation_end: date
    strength: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    evidence_coverage: float = Field(ge=0, le=1)
    hiring_contributor_count: int = Field(ge=0)
    technology_contributor_count: int = Field(ge=0)
    unique_contributing_job_ids: list[UUID]
    supporting_evidence_ids: list[UUID]
    related_hiring_signal_ids: list[UUID]
    related_technology_signal_ids: list[UUID]
    limitations: list[str]
    provenance: StrategicSignalProvenance


class StrategicSignalGenerationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    generated_at: datetime
    coverage_context: StrategicCoverageContext
    signals: list[CrossDomainStrategicSignal] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
