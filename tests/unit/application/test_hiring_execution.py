import asyncio
from datetime import date, datetime, timezone
from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from backend.app.application.hiring import (
    CollectedJob,
    CollectionRequest,
    CollectionStatus,
    ExecutionFailurePhase,
    HiringCollectionExecutionService,
    HiringPersistenceService,
    PersistenceError,
)
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence, SourceType
from backend.app.infrastructure.collectors.hiring.contracts import (
    RawJobPage,
    RawJobRecord,
    SourceIssueStage,
    SourceRecordIssue,
)
from backend.app.infrastructure.collectors.hiring.protocols import SourceAdapterError
from backend.app.infrastructure.persistence.hiring import SQLiteDatabase


RETRIEVED_AT = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)


def run(coroutine):
    return asyncio.run(coroutine)


def raw_record(source_record_id: str = "R-1") -> RawJobRecord:
    return RawJobRecord(
        source_record_id=source_record_id,
        source_url=f"https://careers.example.test/jobs/{source_record_id}",
        retrieved_at=RETRIEVED_AT,
        payload={"title": f"Role {source_record_id}"},
        provenance_metadata={"source": "synthetic"},
    )


class FakeSourceAdapter:
    collector_id = "fake-collector-v1"
    source_id = "fake-career-site"

    def __init__(self, pages=None, error: SourceAdapterError | None = None) -> None:
        self.pages = pages or {}
        self.error = error
        self.cursors = []

    async def fetch_page(self, request, cursor=None):
        self.cursors.append(cursor)
        if self.error is not None:
            raise self.error
        return self.pages[cursor]


class FakeNormalizer:
    def normalize(self, record, request) -> CollectedJob:
        evidence_id = uuid5(NAMESPACE_URL, f"evidence:{record.source_record_id}")
        evidence = Evidence(
            evidence_id=evidence_id,
            source_url=record.source_url,
            source_type=SourceType.CAREER_SITE,
            source_title=record.payload["title"],
            retrieved_at=record.retrieved_at,
            source_excerpt="Synthetic evidence.",
            raw_reference=f"fake:{record.source_record_id}",
            collector_identity="fake-normalizer-v1",
            provenance_metadata=record.provenance_metadata,
        )
        posting = JobPosting(
            job_id=uuid5(NAMESPACE_URL, f"job:{record.source_record_id}"),
            organization=request.organization,
            source_job_id=record.source_record_id,
            title=record.payload["title"],
            description="Synthetic normalized description.",
            location="Charlotte, NC",
            country="US",
            posted_date=date(2026, 8, 1),
            source_url=record.source_url,
            evidence_id=evidence_id,
        )
        return CollectedJob(posting=posting, evidence=evidence)


@pytest.fixture
def database(tmp_path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "execution.sqlite3")
    database.initialize()
    return database


def service(database, adapter):
    persistence = HiringPersistenceService(database.unit_of_work)
    return HiringCollectionExecutionService(
        adapter,
        FakeNormalizer(),
        persistence,
        persistence,
    )


def test_successful_source_neutral_execution_persists_job_evidence_and_run(database):
    request = CollectionRequest(
        organization="Example Bank",
        run_id=UUID("00000000-0000-0000-0000-000000000201"),
    )
    adapter = FakeSourceAdapter({None: RawJobPage(records=[raw_record()])})

    result = run(service(database, adapter).execute(request))

    assert result.status is CollectionStatus.COMPLETED
    assert result.run_id == request.run_id
    assert result.records_collected == 1
    assert result.records_persisted == 1
    with database.unit_of_work() as unit_of_work:
        posting = unit_of_work.job_postings.get_by_source_identity(
            "Example Bank", "R-1"
        )
        evidence = unit_of_work.evidence.get(posting.evidence_id)
        collection_run = unit_of_work.collection_runs.get(request.run_id)
    assert posting.evidence_id == evidence.evidence_id
    assert collection_run.run_id == request.run_id
    assert collection_run.records_collected == 1


def test_partial_collection_persists_valid_jobs_audit_and_resume_cursor(database):
    request = CollectionRequest(
        organization="Example Bank",
        max_pages=1,
    )
    page = RawJobPage(
        records=[raw_record()],
        source_issues=[
            SourceRecordIssue(
                stage=SourceIssueStage.FETCH,
                code="detail_failed",
                message="One detail request failed.",
                source_record_id="R-2",
            )
        ],
        next_cursor="next-page",
    )

    result = run(service(database, FakeSourceAdapter({None: page})).execute(request))

    assert result.status is CollectionStatus.PARTIAL
    assert result.records_encountered == 2
    assert result.records_collected == 1
    assert result.records_skipped == 1
    assert result.records_persisted == 1
    assert result.issue_count == 1
    assert result.resume_cursor == "next-page"
    assert result.collection_result.issues[0].code == "detail_failed"
    with database.unit_of_work() as unit_of_work:
        audit = unit_of_work.collection_runs.get(request.run_id)
        assert len(unit_of_work.job_postings.list_all()) == 1
    assert audit.status is CollectionStatus.PARTIAL
    assert audit.resume_cursor == "next-page"


def test_failed_collection_persists_no_jobs_and_records_failed_audit(database):
    request = CollectionRequest(organization="Example Bank")
    adapter = FakeSourceAdapter(
        error=SourceAdapterError("Source unavailable", code="source_unavailable")
    )

    result = run(service(database, adapter).execute(request))

    assert result.status is CollectionStatus.FAILED
    assert result.collection_status is CollectionStatus.FAILED
    assert result.records_persisted == 0
    assert result.failure.phase is ExecutionFailurePhase.COLLECTION
    with database.unit_of_work() as unit_of_work:
        assert unit_of_work.job_postings.list_all() == []
        audit = unit_of_work.collection_runs.get(request.run_id)
    assert audit.status is CollectionStatus.FAILED


class FailingJobPersistence:
    def save_collected_jobs(self, jobs):
        raise PersistenceError(
            "Synthetic database failure",
            code="database_unavailable",
            metadata={"attempted_jobs": len(jobs)},
        )


class RecordingRunPersistence:
    def __init__(self) -> None:
        self.runs = []

    def save_collection_run(self, collection_run) -> None:
        self.runs.append(collection_run)


def test_persistence_failure_returns_typed_failure_and_attempts_failed_audit():
    run_persistence = RecordingRunPersistence()
    execution = HiringCollectionExecutionService(
        FakeSourceAdapter({None: RawJobPage(records=[raw_record()])}),
        FakeNormalizer(),
        FailingJobPersistence(),
        run_persistence,
    )

    result = run(execution.execute(CollectionRequest(organization="Example Bank")))

    assert result.status is CollectionStatus.FAILED
    assert result.collection_status is CollectionStatus.COMPLETED
    assert result.records_persisted == 0
    assert result.failure.phase is ExecutionFailurePhase.JOB_PERSISTENCE
    assert result.failure.code == "database_unavailable"
    assert len(run_persistence.runs) == 1
    assert run_persistence.runs[0].status is CollectionStatus.FAILED
    assert "execution_failure" in run_persistence.runs[0].source_metadata


def test_repeated_jobs_upsert_while_each_execution_has_distinct_run(database):
    adapter = FakeSourceAdapter({None: RawJobPage(records=[raw_record()])})
    execution = service(database, adapter)
    requests = [
        CollectionRequest(organization="Example Bank"),
        CollectionRequest(organization="Example Bank"),
    ]

    results = [run(execution.execute(request)) for request in requests]

    assert [result.records_persisted for result in results] == [1, 1]
    assert results[0].run_id != results[1].run_id
    with database.unit_of_work() as unit_of_work:
        assert len(unit_of_work.job_postings.list_all()) == 1
        assert len(unit_of_work.evidence.list_all()) == 1
        assert len(unit_of_work.collection_runs.list_recent()) == 2


def test_unexpected_programming_errors_are_not_hidden(database):
    class BrokenNormalizer:
        def normalize(self, record, request):
            raise RuntimeError("programming defect")

    persistence = HiringPersistenceService(database.unit_of_work)
    execution = HiringCollectionExecutionService(
        FakeSourceAdapter({None: RawJobPage(records=[raw_record()])}),
        BrokenNormalizer(),
        persistence,
        persistence,
    )

    with pytest.raises(RuntimeError, match="programming defect"):
        run(execution.execute(CollectionRequest(organization="Example Bank")))
