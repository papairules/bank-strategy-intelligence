from datetime import datetime
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    JsonValue,
    field_validator,
    model_validator,
)


class SourceType(StrEnum):
    CAREER_SITE = "career_site"
    CORPORATE_WEBSITE = "corporate_website"
    FINANCIAL_REPORT = "financial_report"
    NEWS_ARTICLE = "news_article"
    REGULATORY_FILING = "regulatory_filing"
    OTHER = "other"


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: UUID = Field(default_factory=uuid4)
    source_url: HttpUrl
    source_type: SourceType
    source_title: str | None = None
    retrieved_at: datetime
    source_excerpt: str | None = None
    raw_reference: str | None = None
    collector_identity: str = Field(min_length=1)
    provenance_metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("retrieved_at")
    @classmethod
    def require_timezone_aware_retrieval_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def require_excerpt_or_raw_reference(self) -> Self:
        if self.source_excerpt is None and self.raw_reference is None:
            raise ValueError("source_excerpt or raw_reference must be provided")
        return self
