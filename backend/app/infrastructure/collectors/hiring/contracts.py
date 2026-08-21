from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    JsonValue,
    field_validator,
)


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
    next_cursor: str | None = Field(default=None, min_length=1)
    page_metadata: dict[str, JsonValue] = Field(default_factory=dict)
