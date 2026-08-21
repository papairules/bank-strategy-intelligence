from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from backend.app.application.technology import (
    BusinessUnitTechnologyAggregate,
    GeographyTechnologyAggregate,
    SeniorityTechnologyAggregate,
    TechnologyCategoryAggregate,
    TechnologyIntelligenceSnapshot,
    TechnologyObservation,
    TechnologySignal,
    TopTechnologyAggregate,
)


class TechnologySummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: TechnologyIntelligenceSnapshot
    coverage_limitation: str | None


class TechnologyAnalyticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    snapshot: TechnologyIntelligenceSnapshot
    top_technologies: list[TopTechnologyAggregate]
    categories: list[TechnologyCategoryAggregate]
    business_unit_technologies: list[BusinessUnitTechnologyAggregate]
    geography_technologies: list[GeographyTechnologyAggregate]
    seniority_technologies: list[SeniorityTechnologyAggregate]


class TechnologyObservationListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TechnologyObservation]
    total: int = Field(ge=0)
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    returned_count: int = Field(ge=0)


class TechnologySignalsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str
    generated_at: datetime
    total_jobs: int = Field(ge=0)
    enriched_jobs: int = Field(ge=0)
    enrichment_coverage: float = Field(ge=0, le=1)
    technology_observation_count: int = Field(ge=0)
    generated_signal_count: int = Field(ge=0)
    signals: list[TechnologySignal]
    limitations: list[str]
