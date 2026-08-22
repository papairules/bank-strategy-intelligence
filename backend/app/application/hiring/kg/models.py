from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class HiringKGNodeType(StrEnum):
    ORGANIZATION = "Organization"
    JOB = "Job"
    EVIDENCE = "Evidence"
    LOCATION = "Location"
    BUSINESS_UNIT = "BusinessUnit"
    CAPABILITY = "Capability"
    TECHNOLOGY = "Technology"
    SENIORITY = "Seniority"
    HIRING_SIGNAL = "HiringSignal"


class HiringKGEdgeType(StrEnum):
    HAS_JOB = "HAS_JOB"
    SUPPORTED_BY = "SUPPORTED_BY"
    LOCATED_IN = "LOCATED_IN"
    BELONGS_TO = "BELONGS_TO"
    CLASSIFIED_AS = "CLASSIFIED_AS"
    USES_TECHNOLOGY = "USES_TECHNOLOGY"
    HAS_SENIORITY = "HAS_SENIORITY"
    HAS_HIRING_SIGNAL = "HAS_HIRING_SIGNAL"
    ABOUT_CAPABILITY = "ABOUT_CAPABILITY"
    ABOUT_BUSINESS_UNIT = "ABOUT_BUSINESS_UNIT"
    RELATED_TECHNOLOGY = "RELATED_TECHNOLOGY"


class HiringKnowledgeGraphSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    organization: str
    node_count: int = Field(ge=0)
    edge_count: int = Field(ge=0)
    node_counts: dict[HiringKGNodeType, int]
    edge_counts: dict[HiringKGEdgeType, int]
    jobs_read: int = Field(ge=0)
    evidence_records_used: int = Field(ge=0)
    enriched_jobs_used: int = Field(ge=0)
    hiring_signals_used: int = Field(ge=0)
