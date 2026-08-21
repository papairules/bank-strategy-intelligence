from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from backend.app.application.hiring import (
    CollectionIssue,
    CollectionIssueScope,
    CollectionIssueStage,
    CollectionResult,
    CollectionRun,
    CollectionStatus,
    HiringPersistenceService,
)
from backend.app.infrastructure.persistence.hiring import SQLiteDatabase


BASE_TIME = datetime(2026, 8, 20, 12, tzinfo=timezone.utc)


@pytest.fixture
def database(tmp_path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "collection-runs.sqlite3")
    database.initialize()
    return database


def make_issue(index: int = 0) -> CollectionIssue:
    return CollectionIssue(
        stage=CollectionIssueStage.FETCH,
        scope=CollectionIssueScope.PAGE,
        code=f"source_failure_{index}",
        message="Synthetic source failure.",
        recoverable=False,
    )


def make_result(
    *,
    status: CollectionStatus = CollectionStatus.COMPLETED,
    run_id: UUID | None = None,
    organization: str = "Wells Fargo",
    started_at: datetime = BASE_TIME,
    pages_attempted: int = 1,
    records_skipped: int = 0,
    issue_count: int = 0,
    resume_cursor: str | None = None,
) -> CollectionResult:
    return CollectionResult(
        run_id=run_id or uuid4(),
        collector_id="wells-fargo-workday-adapter-v1",
        source_id="wells-fargo-workday",
        organization=organization,
        started_at=started_at,
        completed_at=started_at + timedelta(seconds=5),
        status=status,
        jobs=[],
        issues=[make_issue(index) for index in range(issue_count)],
        pages_attempted=pages_attempted,
        records_encountered=records_skipped,
        records_collected=0,
        records_skipped=records_skipped,
        resume_cursor=resume_cursor,
        source_metadata={
            "pages": [
                {
                    "offset": 0,
                    "limit": 3,
                    "search_http_status": 200,
                }
            ]
        },
    )


@pytest.mark.parametrize(
    ("status", "records_skipped", "issue_count", "resume_cursor"),
    [
        (CollectionStatus.COMPLETED, 0, 0, None),
        (CollectionStatus.PARTIAL, 2, 2, "3"),
        (CollectionStatus.FAILED, 0, 1, None),
    ],
)
def test_collection_result_maps_to_typed_run(
    status,
    records_skipped,
    issue_count,
    resume_cursor,
):
    result = make_result(
        status=status,
        records_skipped=records_skipped,
        issue_count=issue_count,
        resume_cursor=resume_cursor,
    )

    run = CollectionRun.from_collection_result(result)

    assert run.run_id == result.run_id
    assert run.status is status
    assert run.started_at == result.started_at
    assert run.completed_at == result.completed_at
    assert run.pages_attempted == result.pages_attempted
    assert run.records_encountered == result.records_encountered
    assert run.records_collected == result.records_collected
    assert run.records_skipped == result.records_skipped
    assert run.issue_count == len(result.issues)
    assert run.resume_cursor == resume_cursor
    assert run.source_metadata == result.source_metadata


@pytest.mark.parametrize(
    "status",
    [CollectionStatus.COMPLETED, CollectionStatus.PARTIAL, CollectionStatus.FAILED],
)
def test_collection_run_sqlite_round_trip(database, status):
    result = make_result(
        status=status,
        records_skipped=1 if status is CollectionStatus.PARTIAL else 0,
        issue_count=0 if status is CollectionStatus.COMPLETED else 1,
        resume_cursor="next-page" if status is CollectionStatus.PARTIAL else None,
    )
    service = HiringPersistenceService(database.unit_of_work)

    assert service.save_collection_result(result) == 0

    with database.unit_of_work() as unit_of_work:
        retrieved = unit_of_work.collection_runs.get(result.run_id)
    assert retrieved == CollectionRun.from_collection_result(result)
    assert retrieved.run_id == result.run_id


def test_retrieve_run_by_run_id_preserves_counts_metadata_and_cursor(database):
    result = make_result(
        status=CollectionStatus.PARTIAL,
        pages_attempted=4,
        records_skipped=3,
        issue_count=3,
        resume_cursor="60",
    )
    HiringPersistenceService(database.unit_of_work).save_collection_result(result)

    with database.unit_of_work() as unit_of_work:
        retrieved = unit_of_work.collection_runs.get(result.run_id)

    assert retrieved.pages_attempted == 4
    assert retrieved.records_encountered == 3
    assert retrieved.records_skipped == 3
    assert retrieved.issue_count == 3
    assert retrieved.resume_cursor == "60"
    assert retrieved.source_metadata["pages"][0]["search_http_status"] == 200


def test_recent_runs_are_newest_first_and_limited(database):
    results = [
        make_result(started_at=BASE_TIME + timedelta(hours=index))
        for index in range(3)
    ]
    service = HiringPersistenceService(database.unit_of_work)
    for result in results:
        service.save_collection_result(result)

    with database.unit_of_work() as unit_of_work:
        recent = unit_of_work.collection_runs.list_recent(limit=2)

    assert [run.run_id for run in recent] == [results[2].run_id, results[1].run_id]


def test_runs_can_be_filtered_by_organization(database):
    wells_fargo_runs = [
        make_result(organization="Wells Fargo", started_at=BASE_TIME),
        make_result(
            organization="Wells Fargo",
            started_at=BASE_TIME + timedelta(hours=2),
        ),
    ]
    other_run = make_result(
        organization="Example Bank",
        started_at=BASE_TIME + timedelta(hours=1),
    )
    service = HiringPersistenceService(database.unit_of_work)
    for result in [*wells_fargo_runs, other_run]:
        service.save_collection_result(result)

    with database.unit_of_work() as unit_of_work:
        filtered = unit_of_work.collection_runs.list_by_organization("Wells Fargo")
        all_runs = unit_of_work.collection_runs.list_recent()

    assert [run.run_id for run in filtered] == [
        wells_fargo_runs[1].run_id,
        wells_fargo_runs[0].run_id,
    ]
    assert len(all_runs) == 3


def test_collection_run_upsert_is_idempotent(database):
    result = make_result()
    service = HiringPersistenceService(database.unit_of_work)
    service.save_collection_result(result)
    updated = result.model_copy(
        update={
            "status": CollectionStatus.PARTIAL,
            "resume_cursor": "3",
        }
    )

    service.save_collection_result(updated)

    with database.unit_of_work() as unit_of_work:
        runs = unit_of_work.collection_runs.list_recent()
    assert len(runs) == 1
    assert runs[0].run_id == result.run_id
    assert runs[0].status is CollectionStatus.PARTIAL
    assert runs[0].resume_cursor == "3"
