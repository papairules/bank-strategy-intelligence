from backend.app.infrastructure.collectors.hiring.contracts import (
    RawJobPage,
    RawJobRecord,
)
from backend.app.infrastructure.collectors.hiring.protocols import SourceAdapter

__all__ = ["RawJobPage", "RawJobRecord", "SourceAdapter"]
