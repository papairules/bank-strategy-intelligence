from datetime import date, datetime
from enum import StrEnum
from typing import Protocol, Self
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence


class CollectionStatus(StrEnum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class CollectionIssueStage(StrEnum):
    FETCH = "fetch"
    PARSE = "parse"
    NORMALIZE = "normalize"
    VALIDATE = "validate"


class CollectionIssueScope(StrEnum):
    RUN = "run"
    PAGE = "page"
    RECORD = "record"


class CollectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization: str = Field(min_length=1)
    posted_after: date | None = None
    resume_cursor: str | None = Field(default=None, min_length=1)
    max_pages: int | None = Field(default=None, ge=1)
    max_records: int | None = Field(default=None, ge=1)
    run_id: UUID = Field(default_factory=uuid4)

    @field_validator("organization")
    @classmethod
    def normalize_organization(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("organization must not be blank")
        return value


class CollectedJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    posting: JobPosting
    evidence: Evidence

    @model_validator(mode="after")
    def validate_evidence_link(self) -> Self:
        if self.posting.evidence_id != self.evidence.evidence_id:
            raise ValueError("posting evidence_id must match evidence evidence_id")
        return self


class CollectionIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: CollectionIssueStage
    scope: CollectionIssueScope
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    recoverable: bool
    source_record_id: str | None = None
    record_position: int | None = Field(default=None, ge=0)
    page_cursor: str | None = None
    exception_type: str | None = None
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class CollectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    collector_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    organization: str = Field(min_length=1)
    started_at: datetime
    completed_at: datetime
    status: CollectionStatus
    jobs: list[CollectedJob] = Field(default_factory=list)
    issues: list[CollectionIssue] = Field(default_factory=list)
    pages_attempted: int = Field(ge=0)
    records_encountered: int = Field(ge=0)
    records_collected: int = Field(ge=0)
    records_skipped: int = Field(ge=0)
    resume_cursor: str | None = Field(default=None, min_length=1)
    source_metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_timezone_aware_timestamps(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collection timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_counts_and_timestamps(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must be on or after started_at")
        if self.records_collected != len(self.jobs):
            raise ValueError("records_collected must equal the number of jobs")
        if self.records_encountered != self.records_collected + self.records_skipped:
            raise ValueError(
                "records_encountered must equal records_collected plus records_skipped"
            )
        if any(job.posting.organization != self.organization for job in self.jobs):
            raise ValueError("collected job organization must match collection organization")
        return self


class JobCollector(Protocol):
    @property
    def collector_id(self) -> str: ...

    @property
    def source_id(self) -> str: ...

    async def collect(self, request: CollectionRequest) -> CollectionResult: ...
