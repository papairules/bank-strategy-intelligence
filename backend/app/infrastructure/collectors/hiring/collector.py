from collections.abc import Callable
from datetime import datetime, timezone

from pydantic import JsonValue, ValidationError

from backend.app.application.hiring import (
    CollectedJob,
    CollectionIssue,
    CollectionIssueScope,
    CollectionIssueStage,
    CollectionRequest,
    CollectionResult,
    CollectionStatus,
)
from backend.app.infrastructure.collectors.hiring.protocols import (
    JobRecordNormalizer,
    RecordNormalizationError,
    SourceAdapter,
    SourceAdapterError,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PaginatedJobCollector:
    def __init__(
        self,
        adapter: SourceAdapter,
        normalizer: JobRecordNormalizer,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._adapter = adapter
        self._normalizer = normalizer
        self._clock = clock

    @property
    def collector_id(self) -> str:
        return self._adapter.collector_id

    @property
    def source_id(self) -> str:
        return self._adapter.source_id

    async def collect(self, request: CollectionRequest) -> CollectionResult:
        started_at = self._clock()
        cursor = request.resume_cursor
        seen_cursors: set[str | None] = set()
        jobs: list[CollectedJob] = []
        issues: list[CollectionIssue] = []
        page_metadata: list[dict[str, JsonValue]] = []
        pages_attempted = 0
        records_encountered = 0
        records_skipped = 0
        resume_cursor: str | None = None
        natural_completion = False
        terminal_source_failure = False
        stopped_by_limit = False

        while True:
            if cursor in seen_cursors:
                issues.append(
                    CollectionIssue(
                        stage=CollectionIssueStage.FETCH,
                        scope=CollectionIssueScope.PAGE,
                        code="repeated_cursor",
                        message="The source returned a cursor that was already visited.",
                        recoverable=False,
                        page_cursor=cursor,
                    )
                )
                terminal_source_failure = True
                break

            seen_cursors.add(cursor)
            pages_attempted += 1

            try:
                page = await self._adapter.fetch_page(request, cursor)
            except SourceAdapterError as error:
                issues.append(
                    CollectionIssue(
                        stage=error.stage,
                        scope=CollectionIssueScope.PAGE,
                        code=error.code,
                        message=str(error),
                        recoverable=error.recoverable,
                        page_cursor=cursor,
                        exception_type=type(error).__name__,
                        metadata=error.metadata,
                    )
                )
                terminal_source_failure = True
                break

            page_metadata.append(page.page_metadata)

            for record in page.records:
                if (
                    request.max_records is not None
                    and records_encountered >= request.max_records
                ):
                    stopped_by_limit = True
                    resume_cursor = page.next_cursor
                    break

                records_encountered += 1

                try:
                    jobs.append(self._normalizer.normalize(record, request))
                except RecordNormalizationError as error:
                    records_skipped += 1
                    issues.append(
                        CollectionIssue(
                            stage=CollectionIssueStage.NORMALIZE,
                            scope=CollectionIssueScope.RECORD,
                            code=error.code,
                            message=str(error),
                            recoverable=True,
                            source_record_id=record.source_record_id,
                            page_cursor=cursor,
                            exception_type=type(error).__name__,
                            metadata=error.metadata,
                        )
                    )
                except ValidationError as error:
                    records_skipped += 1
                    issues.append(
                        CollectionIssue(
                            stage=CollectionIssueStage.VALIDATE,
                            scope=CollectionIssueScope.RECORD,
                            code="invalid_normalized_record",
                            message=str(error),
                            recoverable=True,
                            source_record_id=record.source_record_id,
                            page_cursor=cursor,
                            exception_type=type(error).__name__,
                        )
                    )

            if stopped_by_limit:
                break

            if page.next_cursor is None:
                natural_completion = True
                break

            if (
                request.max_records is not None
                and records_encountered >= request.max_records
            ):
                stopped_by_limit = True
                resume_cursor = page.next_cursor
                break

            if request.max_pages is not None and pages_attempted >= request.max_pages:
                stopped_by_limit = True
                resume_cursor = page.next_cursor
                break

            cursor = page.next_cursor

        status = self._resolve_status(
            jobs=jobs,
            issues=issues,
            natural_completion=natural_completion,
            terminal_source_failure=terminal_source_failure,
            stopped_by_limit=stopped_by_limit,
        )

        return CollectionResult(
            run_id=request.run_id,
            collector_id=self.collector_id,
            source_id=self.source_id,
            organization=request.organization,
            started_at=started_at,
            completed_at=self._clock(),
            status=status,
            jobs=jobs,
            issues=issues,
            pages_attempted=pages_attempted,
            records_encountered=records_encountered,
            records_collected=len(jobs),
            records_skipped=records_skipped,
            resume_cursor=resume_cursor,
            source_metadata={"pages": page_metadata},
        )

    @staticmethod
    def _resolve_status(
        *,
        jobs: list[CollectedJob],
        issues: list[CollectionIssue],
        natural_completion: bool,
        terminal_source_failure: bool,
        stopped_by_limit: bool,
    ) -> CollectionStatus:
        if terminal_source_failure and not jobs:
            return CollectionStatus.FAILED
        if natural_completion and not issues:
            return CollectionStatus.COMPLETED
        if issues or stopped_by_limit or terminal_source_failure:
            return CollectionStatus.PARTIAL
        return CollectionStatus.COMPLETED
