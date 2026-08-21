from typing import Protocol

from pydantic import JsonValue

from backend.app.application.hiring import (
    CollectedJob,
    CollectionIssueStage,
    CollectionRequest,
)
from backend.app.infrastructure.collectors.hiring.contracts import (
    RawJobPage,
    RawJobRecord,
)


class SourceAdapterError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "source_page_error",
        stage: CollectionIssueStage = CollectionIssueStage.FETCH,
        recoverable: bool = False,
        metadata: dict[str, JsonValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.stage = stage
        self.recoverable = recoverable
        self.metadata = metadata or {}


class RecordNormalizationError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str = "record_normalization_error",
        metadata: dict[str, JsonValue] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.metadata = metadata or {}


class SourceAdapter(Protocol):
    @property
    def collector_id(self) -> str: ...

    @property
    def source_id(self) -> str: ...

    async def fetch_page(
        self,
        request: CollectionRequest,
        cursor: str | None = None,
    ) -> RawJobPage: ...


class JobRecordNormalizer(Protocol):
    def normalize(
        self,
        record: RawJobRecord,
        request: CollectionRequest,
    ) -> CollectedJob: ...
