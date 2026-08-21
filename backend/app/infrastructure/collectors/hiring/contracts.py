from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    JsonValue,
    field_validator,
    model_validator,
)


class SourceIssueStage(StrEnum):
    FETCH = "fetch"
    PARSE = "parse"


class SourceRecordIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: SourceIssueStage
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    recoverable: bool = True
    source_record_id: str | None = Field(default=None, min_length=1)
    record_position: int | None = Field(default=None, ge=0)
    exception_type: str | None = Field(default=None, min_length=1)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_record_context(self) -> Self:
        if self.source_record_id is None and self.record_position is None:
            raise ValueError("source_record_id or record_position must be provided")
        return self


class RawJobRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_record_id: str = Field(min_length=1)
    source_url: HttpUrl
    retrieved_at: datetime
    payload: dict[str, JsonValue]
    source_title: str | None = None
    source_excerpt: str | None = None
    raw_reference: str | None = None
    provenance_metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("retrieved_at")
    @classmethod
    def require_timezone_aware_retrieval_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        return value


class RawJobPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    records: list[RawJobRecord] = Field(default_factory=list)
    source_issues: list[SourceRecordIssue] = Field(default_factory=list)
    next_cursor: str | None = Field(default=None, min_length=1)
    page_metadata: dict[str, JsonValue] = Field(default_factory=dict)
