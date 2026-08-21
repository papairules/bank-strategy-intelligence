from backend.app.infrastructure.collectors.hiring.collector import PaginatedJobCollector
from backend.app.infrastructure.collectors.hiring.contracts import (
    RawJobPage,
    RawJobRecord,
    SourceIssueStage,
    SourceRecordIssue,
)
from backend.app.infrastructure.collectors.hiring.protocols import (
    JobRecordNormalizer,
    RecordNormalizationError,
    SourceAdapter,
    SourceAdapterError,
)

__all__ = [
    "JobRecordNormalizer",
    "PaginatedJobCollector",
    "RawJobPage",
    "RawJobRecord",
    "RecordNormalizationError",
    "SourceAdapter",
    "SourceAdapterError",
    "SourceIssueStage",
    "SourceRecordIssue",
]
