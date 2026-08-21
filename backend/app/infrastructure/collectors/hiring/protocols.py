from typing import Protocol

from backend.app.application.hiring import CollectionRequest
from backend.app.infrastructure.collectors.hiring.contracts import RawJobPage


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
