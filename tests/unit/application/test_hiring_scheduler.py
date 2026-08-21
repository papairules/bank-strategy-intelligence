import asyncio
from datetime import datetime, timedelta, timezone

from backend.app.application.hiring import (
    CollectionRequest,
    CollectionResult,
    CollectionStatus,
    ExecutionFailure,
    ExecutionFailurePhase,
    HiringCollectionExecutionResult,
    HiringCollectionScheduler,
    IntervalCadence,
    ScheduledHiringJob,
)


BASE_TIME = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)


def run(coroutine):
    return asyncio.run(coroutine)


class MutableClock:
    def __init__(self, value: datetime = BASE_TIME) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value

    def advance(self, *, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


def scheduled_job(**updates) -> ScheduledHiringJob:
    values = {
        "job_id": "example-hiring",
        "organization": "Example Bank",
        "enabled": True,
        "cadence": IntervalCadence(seconds=300),
        "max_pages": 2,
        "max_records": 10,
        **updates,
    }
    return ScheduledHiringJob(**values)


def execution_result(
    request: CollectionRequest,
    status: CollectionStatus,
) -> HiringCollectionExecutionResult:
    collection = CollectionResult(
        run_id=request.run_id,
        collector_id="fake-collector",
        source_id="fake-source",
        organization=request.organization,
        started_at=BASE_TIME,
        completed_at=BASE_TIME + timedelta(seconds=1),
        status=status,
        jobs=[],
        issues=[],
        pages_attempted=1,
        records_encountered=0,
        records_collected=0,
        records_skipped=0,
    )
    failure = (
        ExecutionFailure(
            phase=ExecutionFailurePhase.COLLECTION,
            code="synthetic_failure",
            message="Synthetic collection failure.",
        )
        if status is CollectionStatus.FAILED
        else None
    )
    return HiringCollectionExecutionResult(
        run_id=request.run_id,
        status=status,
        collection_status=status,
        pages_attempted=1,
        records_encountered=0,
        records_collected=0,
        records_skipped=0,
        records_persisted=0,
        issue_count=0,
        started_at=collection.started_at,
        completed_at=collection.completed_at,
        collection_result=collection,
        failure=failure,
    )


class FakeExecutionTarget:
    def __init__(self, outcomes=None) -> None:
        self.outcomes = list(outcomes or [CollectionStatus.COMPLETED])
        self.requests = []

    async def execute(self, request):
        self.requests.append(request)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return execution_result(request, outcome)


def scheduler(job, target, clock):
    return HiringCollectionScheduler(
        [job],
        {job.job_id: target},
        clock=clock,
    )


def test_job_due_not_due_and_disabled_states():
    job = scheduled_job()
    assert job.is_due(BASE_TIME) is True

    job.last_started_at = BASE_TIME
    job.last_completed_at = BASE_TIME
    assert job.is_due(BASE_TIME + timedelta(seconds=299)) is False
    assert job.is_due(BASE_TIME + timedelta(seconds=300)) is True

    job.enabled = False
    assert job.is_due(BASE_TIME + timedelta(days=1)) is False


def test_first_execution_constructs_request_and_updates_success_state():
    clock = MutableClock()
    job = scheduled_job()
    target = FakeExecutionTarget()

    outcomes = run(scheduler(job, target, clock).run_due_jobs())

    assert len(outcomes) == 1
    request = target.requests[0]
    assert request.organization == "Example Bank"
    assert request.max_pages == 2
    assert request.max_records == 10
    assert outcomes[0].run_id == request.run_id
    assert job.last_run_id == request.run_id
    assert job.last_status is CollectionStatus.COMPLETED
    assert job.last_started_at == BASE_TIME
    assert job.last_completed_at == BASE_TIME


def test_no_execution_before_interval_and_repeated_execution_when_due():
    clock = MutableClock()
    job = scheduled_job()
    target = FakeExecutionTarget(
        [CollectionStatus.COMPLETED, CollectionStatus.COMPLETED]
    )
    hiring_scheduler = scheduler(job, target, clock)

    assert len(run(hiring_scheduler.run_due_jobs())) == 1
    clock.advance(seconds=299)
    assert run(hiring_scheduler.run_due_jobs()) == []
    clock.advance(seconds=1)
    assert len(run(hiring_scheduler.run_due_jobs())) == 1
    assert len(target.requests) == 2
    assert target.requests[0].run_id != target.requests[1].run_id


def test_partial_and_failed_results_update_scheduler_state():
    for status in (CollectionStatus.PARTIAL, CollectionStatus.FAILED):
        clock = MutableClock()
        job = scheduled_job()
        outcome = run(
            scheduler(job, FakeExecutionTarget([status]), clock).run_due_jobs()
        )[0]
        assert outcome.status is status
        assert job.last_status is status
        assert job.last_run_id == outcome.run_id


def test_one_exception_does_not_prevent_later_execution():
    clock = MutableClock()
    job = scheduled_job()
    target = FakeExecutionTarget(
        [RuntimeError("temporary scheduler target failure"), CollectionStatus.COMPLETED]
    )
    hiring_scheduler = scheduler(job, target, clock)

    first = run(hiring_scheduler.run_due_jobs())[0]
    assert first.status is CollectionStatus.FAILED
    assert first.error_type == "RuntimeError"
    assert job.last_status is CollectionStatus.FAILED

    clock.advance(seconds=300)
    second = run(hiring_scheduler.run_due_jobs())[0]
    assert second.status is CollectionStatus.COMPLETED
    assert job.last_status is CollectionStatus.COMPLETED


def test_same_job_cannot_overlap_within_process():
    clock = MutableClock()
    job = scheduled_job()
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingTarget:
        def __init__(self) -> None:
            self.requests = []

        async def execute(self, request):
            self.requests.append(request)
            started.set()
            await release.wait()
            return execution_result(request, CollectionStatus.COMPLETED)

    target = BlockingTarget()
    hiring_scheduler = scheduler(job, target, clock)

    async def scenario():
        first = asyncio.create_task(hiring_scheduler.run_due_jobs())
        await started.wait()
        overlapping = await hiring_scheduler.run_due_jobs()
        release.set()
        completed = await first
        return overlapping, completed

    overlapping, completed = run(scenario())
    assert overlapping == []
    assert len(completed) == 1
    assert len(target.requests) == 1


def test_scheduler_does_not_start_implicitly():
    clock = MutableClock()
    job = scheduled_job()
    hiring_scheduler = scheduler(job, FakeExecutionTarget(), clock)

    assert hiring_scheduler.is_running is False
    assert job.last_started_at is None
