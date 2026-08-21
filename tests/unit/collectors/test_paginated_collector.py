import asyncio
from datetime import date, datetime, timezone
from uuid import NAMESPACE_URL, uuid5

import pytest

from backend.app.application.hiring import (
    CollectedJob,
    CollectionIssueScope,
    CollectionIssueStage,
    CollectionRequest,
    CollectionStatus,
)
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence, SourceType
from backend.app.infrastructure.collectors.hiring import (
    PaginatedJobCollector,
    RawJobPage,
    RawJobRecord,
    RecordNormalizationError,
    SourceAdapterError,
)


NOW = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


class FakeSourceAdapter:
    collector_id = "fake-careers-v1"
    source_id = "fake-careers"

    def __init__(self, outcomes):
        self._outcomes = outcomes
        self.requested_cursors = []

    async def fetch_page(self, request, cursor=None):
        self.requested_cursors.append(cursor)
        outcome = self._outcomes[cursor]
        if isinstance(outcome, SourceAdapterError):
            raise outcome
        return outcome


class FakeJobNormalizer:
    def normalize(self, record, request):
        if record.payload.get("malformed"):
            raise RecordNormalizationError(
                "The synthetic record is malformed.",
                code="malformed_record",
                metadata={"field": "title"},
            )

        evidence_id = uuid5(
            NAMESPACE_URL,
            f"{request.run_id}:{record.source_record_id}:evidence",
        )
        evidence = Evidence(
            evidence_id=evidence_id,
            source_url=record.source_url,
            source_type=SourceType.CAREER_SITE,
            source_title=record.source_title,
            retrieved_at=record.retrieved_at,
            source_excerpt=record.source_excerpt,
            raw_reference=record.raw_reference or record.source_record_id,
            collector_identity="fake-careers-v1",
            provenance_metadata={
                **record.provenance_metadata,
                "run_id": str(request.run_id),
                "source_record_id": record.source_record_id,
            },
        )
        posting = JobPosting(
            job_id=uuid5(NAMESPACE_URL, f"fake-careers:{record.source_record_id}"),
            organization=request.organization,
            source_job_id=record.source_record_id,
            title=record.payload["title"],
            description=record.payload["description"],
            location=record.payload["location"],
            country=record.payload["country"],
            posted_date=date.fromisoformat(record.payload["posted_date"]),
            source_url=record.source_url,
            evidence_id=evidence_id,
        )
        return CollectedJob(posting=posting, evidence=evidence)


class ProgrammingErrorNormalizer:
    def normalize(self, record, request):
        raise RuntimeError("unexpected bug")


def make_record(record_id, *, malformed=False):
    return RawJobRecord(
        source_record_id=record_id,
        source_url=f"https://careers.example.com/jobs/{record_id}",
        retrieved_at=NOW,
        payload={
            "title": f"Job {record_id}",
            "description": "Build banking technology.",
            "location": "New York, NY",
            "country": "US",
            "posted_date": "2026-08-01",
            "malformed": malformed,
        },
        source_title=f"Job {record_id}",
        source_excerpt="Build banking technology.",
        raw_reference=f"fake:{record_id}",
        provenance_metadata={"fixture": True},
    )


def make_page(*record_ids, next_cursor=None, page_number=1, malformed_ids=()):
    return RawJobPage(
        records=[
            make_record(record_id, malformed=record_id in malformed_ids)
            for record_id in record_ids
        ],
        next_cursor=next_cursor,
        page_metadata={"page": page_number},
    )


def collect(adapter, request=None, normalizer=None):
    collector = PaginatedJobCollector(
        adapter=adapter,
        normalizer=normalizer or FakeJobNormalizer(),
        clock=lambda: NOW,
    )
    return asyncio.run(
        collector.collect(request or CollectionRequest(organization="Example Bank"))
    )


def test_single_page_successful_collection():
    adapter = FakeSourceAdapter({None: make_page("JOB-1", "JOB-2")})

    result = collect(adapter)

    assert result.status is CollectionStatus.COMPLETED
    assert result.pages_attempted == 1
    assert result.records_encountered == 2
    assert result.records_collected == 2
    assert result.records_skipped == 0
    assert result.resume_cursor is None
    assert result.issues == []


def test_multi_page_successful_collection():
    adapter = FakeSourceAdapter(
        {
            None: make_page("JOB-1", next_cursor="cursor-2", page_number=1),
            "cursor-2": make_page("JOB-2", next_cursor="cursor-3", page_number=2),
            "cursor-3": make_page("JOB-3", page_number=3),
        }
    )

    result = collect(adapter)

    assert result.status is CollectionStatus.COMPLETED
    assert adapter.requested_cursors == [None, "cursor-2", "cursor-3"]
    assert result.pages_attempted == 3
    assert result.records_collected == 3
    assert result.source_metadata == {
        "pages": [{"page": 1}, {"page": 2}, {"page": 3}]
    }


def test_collection_starts_from_resume_cursor():
    adapter = FakeSourceAdapter(
        {"cursor-2": make_page("JOB-2", page_number=2)}
    )
    request = CollectionRequest(
        organization="Example Bank",
        resume_cursor="cursor-2",
    )

    result = collect(adapter, request)

    assert adapter.requested_cursors == ["cursor-2"]
    assert result.records_collected == 1
    assert result.status is CollectionStatus.COMPLETED


def test_max_pages_stops_with_resume_cursor():
    adapter = FakeSourceAdapter(
        {
            None: make_page("JOB-1", next_cursor="cursor-2", page_number=1),
            "cursor-2": make_page("JOB-2", page_number=2),
        }
    )
    request = CollectionRequest(organization="Example Bank", max_pages=1)

    result = collect(adapter, request)

    assert adapter.requested_cursors == [None]
    assert result.status is CollectionStatus.PARTIAL
    assert result.pages_attempted == 1
    assert result.records_collected == 1
    assert result.resume_cursor == "cursor-2"


def test_max_records_stops_with_resume_cursor():
    adapter = FakeSourceAdapter(
        {
            None: make_page("JOB-1", next_cursor="cursor-2", page_number=1),
            "cursor-2": make_page("JOB-2", page_number=2),
        }
    )
    request = CollectionRequest(organization="Example Bank", max_records=1)

    result = collect(adapter, request)

    assert adapter.requested_cursors == [None]
    assert result.status is CollectionStatus.PARTIAL
    assert result.records_encountered == 1
    assert result.records_collected == 1
    assert result.resume_cursor == "cursor-2"


def test_repeated_cursor_stops_safely():
    adapter = FakeSourceAdapter(
        {
            None: make_page("JOB-1", next_cursor="cursor-2", page_number=1),
            "cursor-2": make_page(
                "JOB-2",
                next_cursor="cursor-2",
                page_number=2,
            ),
        }
    )

    result = collect(adapter)

    assert adapter.requested_cursors == [None, "cursor-2"]
    assert result.status is CollectionStatus.PARTIAL
    assert result.pages_attempted == 2
    assert result.records_collected == 2
    assert len(result.issues) == 1
    assert result.issues[0].code == "repeated_cursor"
    assert result.issues[0].scope is CollectionIssueScope.PAGE


def test_malformed_record_is_skipped_while_valid_records_survive():
    adapter = FakeSourceAdapter(
        {
            None: make_page(
                "JOB-1",
                "JOB-BAD",
                "JOB-2",
                malformed_ids={"JOB-BAD"},
            )
        }
    )

    result = collect(adapter)

    assert result.status is CollectionStatus.PARTIAL
    assert result.records_encountered == 3
    assert result.records_collected == 2
    assert result.records_skipped == 1
    assert [job.posting.source_job_id for job in result.jobs] == ["JOB-1", "JOB-2"]
    assert result.issues[0].stage is CollectionIssueStage.NORMALIZE
    assert result.issues[0].source_record_id == "JOB-BAD"


def test_page_failure_after_success_returns_partial_result():
    adapter = FakeSourceAdapter(
        {
            None: make_page("JOB-1", next_cursor="cursor-2"),
            "cursor-2": SourceAdapterError(
                "Synthetic page failure.",
                code="page_unavailable",
                recoverable=True,
            ),
        }
    )

    result = collect(adapter)

    assert result.status is CollectionStatus.PARTIAL
    assert result.pages_attempted == 2
    assert result.records_collected == 1
    assert result.issues[0].code == "page_unavailable"
    assert result.issues[0].stage is CollectionIssueStage.FETCH


def test_initial_page_failure_returns_failed_result():
    adapter = FakeSourceAdapter(
        {
            None: SourceAdapterError(
                "Synthetic initial failure.",
                code="source_unavailable",
            )
        }
    )

    result = collect(adapter)

    assert result.status is CollectionStatus.FAILED
    assert result.pages_attempted == 1
    assert result.records_encountered == 0
    assert result.records_collected == 0
    assert result.records_skipped == 0


def test_collected_jobs_preserve_evidence_linkage():
    adapter = FakeSourceAdapter({None: make_page("JOB-1")})

    result = collect(adapter)
    collected_job = result.jobs[0]

    assert collected_job.posting.evidence_id == collected_job.evidence.evidence_id
    assert collected_job.evidence.collector_identity == adapter.collector_id
    assert (
        collected_job.evidence.provenance_metadata["source_record_id"]
        == collected_job.posting.source_job_id
    )


def test_unexpected_programming_errors_are_not_swallowed():
    adapter = FakeSourceAdapter({None: make_page("JOB-1")})

    with pytest.raises(RuntimeError, match="unexpected bug"):
        collect(adapter, normalizer=ProgrammingErrorNormalizer())
