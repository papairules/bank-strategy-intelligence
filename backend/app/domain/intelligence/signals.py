from datetime import date
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class IntelligenceCapability(StrEnum):
    HIRING = "hiring"
    STRATEGY = "strategy"
    TECHNOLOGY = "technology"
    ORGANIZATION = "organization"
    FINANCIAL = "financial"
    NEWS = "news"


class ObservationPeriod(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_date: date
    end_date: date

    @model_validator(mode="after")
    def validate_date_order(self) -> Self:
        if self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class IntelligenceSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: UUID = Field(default_factory=uuid4)
    signal_type: str = Field(min_length=1)
    organization: str = Field(min_length=1)
    originating_capability: IntelligenceCapability
    observation_period: ObservationPeriod
    summary: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    supporting_evidence_ids: list[UUID] = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)
