import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from backend.app.application.hiring.collection import CollectionRequest, CollectionStatus
from backend.app.application.hiring.execution import HiringCollectionExecutionResult


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IntervalCadence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seconds: int = Field(ge=60)


class ScheduledHiringJob(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    job_id: str = Field(min_length=1)
    organization: str = Field(min_length=1)
    enabled: bool = False
    cadence: IntervalCadence
    max_pages: int = Field(ge=1)
    max_records: int = Field(ge=1)
    last_started_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_run_id: UUID | None = None
    last_status: CollectionStatus | None = None

    @field_validator("last_started_at", "last_completed_at")
    @classmethod
    def require_timezone_aware_timestamps(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("scheduler timestamps must be timezone-aware")
        return value

    @model_validator(mode="after")
    def validate_timestamp_order(self):
        if (
            self.last_started_at is not None
            and self.last_completed_at is not None
            and self.last_completed_at < self.last_started_at
        ):
            raise ValueError("last_completed_at must be on or after last_started_at")
        return self

    def is_due(self, now: datetime) -> bool:
        if not self.enabled:
            return False
        reference = self.last_completed_at or self.last_started_at
        if reference is None:
            return True
        return now >= reference + timedelta(seconds=self.cadence.seconds)


class ScheduledExecutionTarget(Protocol):
    async def execute(
        self,
        request: CollectionRequest,
    ) -> HiringCollectionExecutionResult: ...


class ScheduledJobOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    job_id: str
    run_id: UUID
    status: CollectionStatus
    started_at: datetime
    completed_at: datetime
    execution_result: HiringCollectionExecutionResult | None = None
    error_type: str | None = None
    error_message: str | None = None


class HiringCollectionScheduler:
    def __init__(
        self,
        jobs: list[ScheduledHiringJob],
        execution_targets: dict[str, ScheduledExecutionTarget],
        *,
        clock: Callable[[], datetime] = utc_now,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        poll_interval_seconds: float = 30.0,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        job_ids = [job.job_id for job in jobs]
        if len(job_ids) != len(set(job_ids)):
            raise ValueError("scheduled job IDs must be unique")
        missing_targets = set(job_ids) - execution_targets.keys()
        if missing_targets:
            raise ValueError("every scheduled job must have an execution target")
        self._jobs = {job.job_id: job for job in jobs}
        self._execution_targets = execution_targets
        self._clock = clock
        self._sleeper = sleeper
        self._poll_interval_seconds = poll_interval_seconds
        self._execution_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    @property
    def jobs(self) -> list[ScheduledHiringJob]:
        return list(self._jobs.values())

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def run_due_jobs(self) -> list[ScheduledJobOutcome]:
        if self._execution_lock.locked():
            return []
        async with self._execution_lock:
            outcomes: list[ScheduledJobOutcome] = []
            for job in self._jobs.values():
                if job.is_due(self._clock()):
                    outcomes.append(await self._execute_job(job))
            return outcomes

    def start(self) -> None:
        if self.is_running:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self.run_forever())

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None

    async def run_forever(self) -> None:
        while not self._stop_event.is_set():
            await self.run_due_jobs()
            await self._sleeper(self._poll_interval_seconds)

    async def _execute_job(self, job: ScheduledHiringJob) -> ScheduledJobOutcome:
        started_at = self._clock()
        request = CollectionRequest(
            organization=job.organization,
            max_pages=job.max_pages,
            max_records=job.max_records,
        )
        job.last_completed_at = None
        job.last_started_at = started_at
        job.last_run_id = request.run_id
        try:
            result = await self._execution_targets[job.job_id].execute(request)
        except Exception as error:
            completed_at = self._clock()
            job.last_completed_at = completed_at
            job.last_status = CollectionStatus.FAILED
            return ScheduledJobOutcome(
                job_id=job.job_id,
                run_id=request.run_id,
                status=CollectionStatus.FAILED,
                started_at=started_at,
                completed_at=completed_at,
                error_type=type(error).__name__,
                error_message=str(error),
            )

        completed_at = self._clock()
        job.last_completed_at = completed_at
        job.last_run_id = result.run_id
        job.last_status = result.status
        return ScheduledJobOutcome(
            job_id=job.job_id,
            run_id=result.run_id,
            status=result.status,
            started_at=started_at,
            completed_at=completed_at,
            execution_result=result,
        )
