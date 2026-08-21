from datetime import date, datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.app.application.hiring import (
    CollectedJob,
    CollectionIssue,
    CollectionIssueScope,
    CollectionIssueStage,
    CollectionRequest,
    CollectionResult,
    CollectionStatus,
)
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence, SourceType
from backend.app.infrastructure.collectors.hiring import (
    RawJobPage,
    RawJobRecord,
    SourceIssueStage,
    SourceRecordIssue,
)


RUN_ID = UUID("00000000-0000-0000-0000-000000000001")
EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000002")
JOB_ID = UUID("00000000-0000-0000-0000-000000000003")


def make_evidence(evidence_id: UUID = EVIDENCE_ID) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        source_url="https://careers.example.com/jobs/JOB-123",
        source_type=SourceType.CAREER_SITE,
        source_title="Data Engineer",
        retrieved_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        raw_reference="example:JOB-123",
        collector_identity="example-careers-v1",
        provenance_metadata={"run_id": str(RUN_ID), "page": 1},
    )


def make_posting(evidence_id: UUID = EVIDENCE_ID) -> JobPosting:
    return JobPosting(
        job_id=JOB_ID,
        organization="Example Bank",
        source_job_id="JOB-123",
        title="Data Engineer",
        description="Build data products.",
        location="New York, NY",
        country="US",
        posted_date=date(2026, 8, 1),
        source_url="https://careers.example.com/jobs/JOB-123",
        evidence_id=evidence_id,
    )


def test_collection_request_serializes_source_neutral_controls():
    request = CollectionRequest(
        organization="Example Bank",
        posted_after=date(2026, 7, 1),
        resume_cursor="cursor-2",
        max_pages=5,
        max_records=250,
        run_id=RUN_ID,
    )

    assert request.model_dump(mode="json") == {
        "organization": "Example Bank",
        "posted_after": "2026-07-01",
        "resume_cursor": "cursor-2",
        "max_pages": 5,
        "max_records": 250,
        "run_id": str(RUN_ID),
    }


@pytest.mark.parametrize(
    ("field_name", "value"),
    [("max_pages", 0), ("max_pages", -1), ("max_records", 0), ("max_records", -1)],
)
def test_collection_request_rejects_invalid_limits(field_name, value):
    with pytest.raises(ValidationError):
        CollectionRequest(organization="Example Bank", **{field_name: value})


def test_collected_job_requires_matching_evidence_ids():
    with pytest.raises(ValidationError):
        CollectedJob(
            posting=make_posting(),
            evidence=make_evidence(
                UUID("00000000-0000-0000-0000-000000000099")
            ),
        )


def test_raw_job_record_and_page_serialize_opaque_source_data():
    record = RawJobRecord(
        source_record_id="JOB-123",
        source_url="https://careers.example.com/jobs/JOB-123",
        retrieved_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        payload={
            "requisition": "JOB-123",
            "locations": ["New York", "Charlotte"],
            "remote": False,
        },
        source_title="Data Engineer",
        source_excerpt="Build data products.",
        raw_reference="api-page-1:JOB-123",
        provenance_metadata={"http_status": 200},
    )
    page = RawJobPage(
        records=[record],
        next_cursor="cursor-2",
        page_metadata={"page": 1, "endpoint": "/jobs/search"},
    )

    assert page.model_dump(mode="json") == {
        "records": [
            {
                "source_record_id": "JOB-123",
                "source_url": "https://careers.example.com/jobs/JOB-123",
                "retrieved_at": "2026-08-20T12:00:00Z",
                "payload": {
                    "requisition": "JOB-123",
                    "locations": ["New York", "Charlotte"],
                    "remote": False,
                },
                "source_title": "Data Engineer",
                "source_excerpt": "Build data products.",
                "raw_reference": "api-page-1:JOB-123",
                "provenance_metadata": {"http_status": 200},
            }
        ],
        "source_issues": [],
        "next_cursor": "cursor-2",
        "page_metadata": {"page": 1, "endpoint": "/jobs/search"},
    }


def test_raw_job_page_source_issues_serialize_and_validate():
    issue = SourceRecordIssue(
        stage=SourceIssueStage.FETCH,
        code="detail_unavailable",
        message="The source detail could not be retrieved.",
        recoverable=True,
        source_record_id="JOB-456",
        record_position=3,
        exception_type="TimeoutError",
        metadata={"http_status": 504},
    )
    page = RawJobPage(
        source_issues=[issue],
        next_cursor="cursor-2",
        page_metadata={"page": 1},
    )

    assert page.model_dump(mode="json") == {
        "records": [],
        "source_issues": [
            {
                "stage": "fetch",
                "code": "detail_unavailable",
                "message": "The source detail could not be retrieved.",
                "recoverable": True,
                "source_record_id": "JOB-456",
                "record_position": 3,
                "exception_type": "TimeoutError",
                "metadata": {"http_status": 504},
            }
        ],
        "next_cursor": "cursor-2",
        "page_metadata": {"page": 1},
    }

    with pytest.raises(ValidationError):
        SourceRecordIssue(
            stage=SourceIssueStage.PARSE,
            code="invalid_detail",
            message="The source detail was malformed.",
        )

    with pytest.raises(ValidationError):
        SourceRecordIssue(
            stage=SourceIssueStage.PARSE,
            code="invalid_detail",
            message="The source detail was malformed.",
            record_position=-1,
        )


def test_raw_job_record_requires_aware_timestamp_and_json_payload():
    with pytest.raises(ValidationError):
        RawJobRecord(
            source_record_id="JOB-123",
            source_url="https://careers.example.com/jobs/JOB-123",
            retrieved_at=datetime(2026, 8, 20, 12, 0),
            payload={"posted_at": date(2026, 8, 1)},
        )


def test_collection_issue_and_status_enums_serialize():
    issue = CollectionIssue(
        stage=CollectionIssueStage.VALIDATE,
        scope=CollectionIssueScope.RECORD,
        code="invalid_posted_date",
        message="The posting date could not be parsed.",
        recoverable=True,
        source_record_id="JOB-456",
        page_cursor="cursor-2",
        exception_type="ValidationError",
        metadata={"field": "postedDate"},
    )

    assert issue.model_dump(mode="json") == {
        "stage": "validate",
        "scope": "record",
        "code": "invalid_posted_date",
        "message": "The posting date could not be parsed.",
        "recoverable": True,
        "source_record_id": "JOB-456",
        "record_position": None,
        "page_cursor": "cursor-2",
        "exception_type": "ValidationError",
        "metadata": {"field": "postedDate"},
    }

    with pytest.raises(ValidationError):
        CollectionIssue(
            stage="unknown",
            scope="unknown",
            code="bad_issue",
            message="Invalid enum values.",
            recoverable=False,
        )


def test_collection_result_serializes_run_metadata_and_counts():
    collected_job = CollectedJob(posting=make_posting(), evidence=make_evidence())
    issue = CollectionIssue(
        stage=CollectionIssueStage.PARSE,
        scope=CollectionIssueScope.RECORD,
        code="malformed_record",
        message="One source record was malformed.",
        recoverable=True,
        source_record_id="JOB-456",
    )
    result = CollectionResult(
        run_id=RUN_ID,
        collector_id="example-careers-v1",
        source_id="example-careers",
        organization="Example Bank",
        started_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        completed_at=datetime(2026, 8, 20, 12, 1, tzinfo=timezone.utc),
        status=CollectionStatus.PARTIAL,
        jobs=[collected_job],
        issues=[issue],
        pages_attempted=2,
        records_encountered=2,
        records_collected=1,
        records_skipped=1,
        resume_cursor="cursor-3",
        source_metadata={"endpoint": "/jobs/search", "content_type": "application/json"},
    )
    serialized = result.model_dump(mode="json")

    assert serialized["run_id"] == str(RUN_ID)
    assert serialized["status"] == "partial"
    assert serialized["records_collected"] == 1
    assert serialized["jobs"][0]["posting"]["evidence_id"] == str(EVIDENCE_ID)
    assert serialized["jobs"][0]["evidence"]["evidence_id"] == str(EVIDENCE_ID)
    assert serialized["source_metadata"] == {
        "endpoint": "/jobs/search",
        "content_type": "application/json",
    }


def test_collection_result_rejects_inconsistent_counts():
    with pytest.raises(ValidationError):
        CollectionResult(
            run_id=RUN_ID,
            collector_id="example-careers-v1",
            source_id="example-careers",
            organization="Example Bank",
            started_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 8, 20, 12, 1, tzinfo=timezone.utc),
            status=CollectionStatus.COMPLETED,
            jobs=[],
            issues=[],
            pages_attempted=1,
            records_encountered=1,
            records_collected=1,
            records_skipped=0,
        )
