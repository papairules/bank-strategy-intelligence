from datetime import date
from enum import StrEnum
from typing import Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    INTERNSHIP = "internship"
    OTHER = "other"


class SeniorityLevel(StrEnum):
    ENTRY = "entry"
    MID = "mid"
    SENIOR = "senior"
    MANAGER = "manager"
    DIRECTOR = "director"
    EXECUTIVE = "executive"


class JobPosting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: UUID = Field(default_factory=uuid4)
    organization: str = Field(min_length=1)
    source_job_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str = Field(min_length=1)
    location: str = Field(min_length=1)
    country: str = Field(min_length=1)
    business_unit: str | None = None
    capability_classifications: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    technologies: list[str] = Field(default_factory=list)
    seniority_level: SeniorityLevel | None = None
    is_leadership: bool = False
    posted_date: date
    closing_date: date | None = None
    employment_type: EmploymentType | None = None
    source_url: HttpUrl
    evidence_id: UUID

    @model_validator(mode="after")
    def validate_date_order(self) -> Self:
        if self.closing_date is not None and self.closing_date < self.posted_date:
            raise ValueError("closing_date must be on or after posted_date")
        return self
