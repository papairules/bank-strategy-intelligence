from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.application.hiring import EnrichmentSeniority
from backend.app.domain.intelligence import SourceType


class TechnologyCategory(StrEnum):
    PROGRAMMING_LANGUAGE = "Programming Language"
    DATABASE = "Database"
    DATA_PLATFORM = "Data Platform"
    CLOUD_PLATFORM = "Cloud Platform"
    BI_VISUALIZATION = "BI / Visualization"
    ANALYTICS_STATISTICAL_TOOL = "Analytics / Statistical Tool"
    DATA_ENGINEERING = "Data Engineering"
    AI_ML = "AI / ML"
    DEVOPS_INFRASTRUCTURE = "DevOps / Infrastructure"
    ENTERPRISE_PLATFORM = "Enterprise Platform"
    OTHER = "Other"


class TechnologyRecordReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    job_id: UUID
    evidence_id: UUID


class TechnologyProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    prompt_schema_version: str
    enrichment_timestamp: datetime


class TechnologySupportReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID
    excerpt: str | None = None


class TechnologyObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technology: str
    normalized_technology: str
    category: TechnologyCategory
    organization: str
    job_id: UUID
    job_title: str
    evidence_id: UUID
    source_type: SourceType
    observation_date: date
    location: str
    business_unit: str | None = None
    seniority: EnrichmentSeniority
    confidence: float = Field(ge=0, le=1)
    provenance: TechnologyProvenance
    support_references: list[TechnologySupportReference] = Field(default_factory=list)


class TechnologyIntelligenceSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    total_jobs: int = Field(ge=0)
    enriched_jobs: int = Field(ge=0)
    technology_observation_count: int = Field(ge=0)
    unique_technologies: int = Field(ge=0)
    technology_coverage_percentage: float = Field(ge=0, le=100)
    jobs_with_technology_signal: int = Field(ge=0)
    technology_signal_coverage_percentage: float = Field(ge=0, le=100)
    observation_start: date | None = None
    observation_end: date | None = None
    generated_at: datetime


class TopTechnologyAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technology: str
    category: TechnologyCategory
    job_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    percentage_of_enriched_jobs: float = Field(ge=0, le=100)
    percentage_of_technology_classified_jobs: float = Field(ge=0, le=100)
    evidence_count: int = Field(ge=0)
    contributing_records: list[TechnologyRecordReference]


class TechnologyCategoryAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: TechnologyCategory
    unique_technology_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    job_count: int = Field(ge=0)
    contributing_records: list[TechnologyRecordReference]


class BusinessUnitTechnologyAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_unit: str
    technology: str
    job_count: int = Field(ge=0)
    contributing_records: list[TechnologyRecordReference]


class GeographyTechnologyAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    location: str
    technology: str
    job_count: int = Field(ge=0)
    contributing_records: list[TechnologyRecordReference]


class SeniorityTechnologyAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seniority: EnrichmentSeniority
    technology: str
    job_count: int = Field(ge=0)
    contributing_records: list[TechnologyRecordReference]


class TechnologyAnalyticsResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: TechnologyIntelligenceSnapshot
    top_technologies: list[TopTechnologyAggregate]
    categories: list[TechnologyCategoryAggregate]
    business_unit_technologies: list[BusinessUnitTechnologyAggregate]
    geography_technologies: list[GeographyTechnologyAggregate]
    seniority_technologies: list[SeniorityTechnologyAggregate]
