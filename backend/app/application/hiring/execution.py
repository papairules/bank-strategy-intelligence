from datetime import datetime
from enum import StrEnum
from typing import Protocol, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from backend.app.application.hiring.collection import (
    CollectedJob,
    CollectionRequest,
    CollectionResult,
    CollectionStatus,
)
from backend.app.application.hiring.observability import CollectionRun
from backend.app.application.hiring.persistence import PersistenceError
from backend.app.infrastructure.collectors.hiring.collector import PaginatedJobCollector
from backend.app.infrastructure.collectors.hiring.protocols import (
    JobRecordNormalizer,
    SourceAdapter,
)


class ExecutionFailurePhase(StrEnum):
    COLLECTION = "collection"
    JOB_PERSISTENCE = "job_persistence"
    RUN_PERSISTENCE = "run_persistence"


class ExecutionFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase: ExecutionFailurePhase
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    metadata: dict[str, JsonValue] = Field(default_factory=dict)


class HiringCollectionExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    status: CollectionStatus
    collection_status: CollectionStatus
    pages_attempted: int = Field(ge=0)
    records_encountered: int = Field(ge=0)
    records_collected: int = Field(ge=0)
    records_skipped: int = Field(ge=0)
    records_persisted: int = Field(ge=0)
    issue_count: int = Field(ge=0)
    resume_cursor: str | None = Field(default=None, min_length=1)
    started_at: datetime
    completed_at: datetime
    collection_result: CollectionResult
    failure: ExecutionFailure | None = None

    @model_validator(mode="after")
    def require_failure_for_failed_execution(self) -> Self:
        if self.status is CollectionStatus.FAILED and self.failure is None:
            raise ValueError("failed execution must include failure context")
        return self


class CollectedJobPersistence(Protocol):
    def save_collected_jobs(self, jobs: list[CollectedJob]) -> int: ...


class CollectionRunPersistence(Protocol):
    def save_collection_run(self, run: CollectionRun) -> None: ...


class HiringCollectionExecutionService:
    def __init__(
        self,
        adapter: SourceAdapter,
        normalizer: JobRecordNormalizer,
        job_persistence: CollectedJobPersistence,
        run_persistence: CollectionRunPersistence,
    ) -> None:
        self._collector = PaginatedJobCollector(adapter, normalizer)
        self._job_persistence = job_persistence
        self._run_persistence = run_persistence

    async def execute(
        self,
        request: CollectionRequest,
    ) -> HiringCollectionExecutionResult:
        collection_result = await self._collector.collect(request)
        collection_run = CollectionRun.from_collection_result(collection_result)

        try:
            records_persisted = self._job_persistence.save_collected_jobs(
                collection_result.jobs
            )
        except PersistenceError as error:
            failed_run = self._failed_persistence_run(
                collection_run,
                phase=ExecutionFailurePhase.JOB_PERSISTENCE,
                error=error,
            )
            audit_error = self._persist_failure_run(failed_run)
            metadata: dict[str, JsonValue] = dict(error.metadata)
            if audit_error is not None:
                metadata["audit_error_code"] = audit_error.code
                metadata["audit_error_message"] = str(audit_error)
            return self._execution_result(
                collection_run,
                collection_result=collection_result,
                status=CollectionStatus.FAILED,
                records_persisted=0,
                failure=ExecutionFailure(
                    phase=ExecutionFailurePhase.JOB_PERSISTENCE,
                    code=error.code,
                    message=str(error),
                    metadata=metadata,
                ),
            )

        try:
            self._run_persistence.save_collection_run(collection_run)
        except PersistenceError as error:
            return self._execution_result(
                collection_run,
                collection_result=collection_result,
                status=CollectionStatus.FAILED,
                records_persisted=records_persisted,
                failure=ExecutionFailure(
                    phase=ExecutionFailurePhase.RUN_PERSISTENCE,
                    code=error.code,
                    message=str(error),
                    metadata=error.metadata,
                ),
            )

        if collection_result.status is CollectionStatus.FAILED:
            message = (
                collection_result.issues[0].message
                if collection_result.issues
                else "Collection failed without producing jobs."
            )
            failure = ExecutionFailure(
                phase=ExecutionFailurePhase.COLLECTION,
                code="collection_failed",
                message=message,
                metadata={"issue_count": len(collection_result.issues)},
            )
        else:
            failure = None

        return self._execution_result(
            collection_run,
            collection_result=collection_result,
            status=collection_result.status,
            records_persisted=records_persisted,
            failure=failure,
        )

    def _persist_failure_run(self, run: CollectionRun) -> PersistenceError | None:
        try:
            self._run_persistence.save_collection_run(run)
        except PersistenceError as error:
            return error
        return None

    @staticmethod
    def _failed_persistence_run(
        run: CollectionRun,
        *,
        phase: ExecutionFailurePhase,
        error: PersistenceError,
    ) -> CollectionRun:
        source_metadata = dict(run.source_metadata)
        source_metadata["execution_failure"] = {
            "phase": phase.value,
            "code": error.code,
            "message": str(error),
            "metadata": error.metadata,
        }
        return run.model_copy(
            update={
                "status": CollectionStatus.FAILED,
                "issue_count": run.issue_count + 1,
                "source_metadata": source_metadata,
            }
        )

    @staticmethod
    def _execution_result(
        run: CollectionRun,
        *,
        collection_result: CollectionResult,
        status: CollectionStatus,
        records_persisted: int,
        failure: ExecutionFailure | None,
    ) -> HiringCollectionExecutionResult:
        return HiringCollectionExecutionResult(
            run_id=run.run_id,
            status=status,
            collection_status=run.status,
            pages_attempted=run.pages_attempted,
            records_encountered=run.records_encountered,
            records_collected=run.records_collected,
            records_skipped=run.records_skipped,
            records_persisted=records_persisted,
            issue_count=run.issue_count,
            resume_cursor=run.resume_cursor,
            started_at=run.started_at,
            completed_at=run.completed_at,
            collection_result=collection_result,
            failure=failure,
        )
