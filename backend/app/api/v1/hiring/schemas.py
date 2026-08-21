from pydantic import BaseModel, ConfigDict, Field

from backend.app.application.hiring import CollectionRun
from backend.app.domain.hiring import JobPosting


class JobPostingListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[JobPosting]
    limit: int = Field(ge=1)
    offset: int = Field(ge=0)
    returned_count: int = Field(ge=0)


class CollectionRunListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CollectionRun]
    limit: int = Field(ge=1)
    returned_count: int = Field(ge=0)
