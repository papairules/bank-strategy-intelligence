from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator, model_validator

from backend.app.application.hiring.collection import CollectionResult, CollectionStatus


class CollectionRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    collector_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    organization: str = Field(min_length=1)
    started_at: datetime
    completed_at: datetime
    status: CollectionStatus
    pages_attempted: int = Field(ge=0)
    records_encountered: int = Field(ge=0)
    records_collected: int = Field(ge=0)
    records_skipped: int = Field(ge=0)
    issue_count: int = Field(ge=0)
    resume_cursor: str | None = Field(default=None, min_length=1)
    source_metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("started_at", "completed_at")
    @classmethod
    def require_timezone_aware_timestamps(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("collection run timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_counts_and_timestamps(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("completed_at must be on or after started_at")
        if self.records_encountered != self.records_collected + self.records_skipped:
            raise ValueError(
                "records_encountered must equal records_collected plus records_skipped"
            )
        return self

    @classmethod
    def from_collection_result(cls, result: CollectionResult) -> Self:
        return cls(
            run_id=result.run_id,
            collector_id=result.collector_id,
            source_id=result.source_id,
            organization=result.organization,
            started_at=result.started_at,
            completed_at=result.completed_at,
            status=result.status,
            pages_attempted=result.pages_attempted,
            records_encountered=result.records_encountered,
            records_collected=result.records_collected,
            records_skipped=result.records_skipped,
            issue_count=len(result.issues),
            resume_cursor=result.resume_cursor,
            source_metadata=result.source_metadata,
        )
