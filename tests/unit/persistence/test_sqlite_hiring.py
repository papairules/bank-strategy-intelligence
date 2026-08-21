from copy import deepcopy
from datetime import datetime, timezone
import sqlite3
from uuid import UUID, uuid4

import pytest

from backend.app.application.hiring import (
    CollectionRequest,
    HiringPersistenceService,
)
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence, SourceType
from backend.app.infrastructure.collectors.hiring.contracts import RawJobRecord
from backend.app.infrastructure.collectors.hiring.sources.wells_fargo.fixtures import (
    part_time,
    standard_us_full_time,
)
from backend.app.infrastructure.collectors.hiring.sources.wells_fargo.normalizer import (
    WellsFargoJobNormalizer,
)
from backend.app.infrastructure.persistence.hiring import SQLiteDatabase


RETRIEVED_AT = datetime(2026, 8, 20, 12, 30, tzinfo=timezone.utc)
RUN_ID = UUID("00000000-0000-0000-0000-000000000100")


@pytest.fixture
def database(tmp_path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "hiring.sqlite3")
    database.initialize()
    return database


def make_evidence(evidence_id: UUID | None = None) -> Evidence:
    return Evidence(
        evidence_id=evidence_id or uuid4(),
        source_url="https://careers.example.test/jobs/R-1",
        source_type=SourceType.CAREER_SITE,
        source_title="Platform Engineer",
        retrieved_at=RETRIEVED_AT,
        source_excerpt="A synthetic source excerpt.",
        raw_reference="career:example:R-1",
        collector_identity="synthetic-test-collector",
        provenance_metadata={"page": 1, "source": "fixture"},
    )


def make_posting(evidence_id: UUID, **updates: object) -> JobPosting:
    values = {
        "organization": "Example Bank",
        "source_job_id": "R-1",
        "title": "Platform Engineer",
        "description": "Build reliable platforms.",
        "location": "Charlotte, NC",
        "country": "US",
        "business_unit": "Technology",
        "capability_classifications": ["platform engineering"],
        "skills": ["systems design"],
        "technologies": ["Python"],
        "seniority_level": "senior",
        "is_leadership": False,
        "posted_date": "2026-08-01",
        "closing_date": "2026-08-31",
        "employment_type": "full_time",
        "source_url": "https://careers.example.test/jobs/R-1",
        "evidence_id": evidence_id,
        **updates,
    }
    return JobPosting.model_validate(values)


def normalize_wells_fargo(payload: dict, source_record_id: str):
    detail = payload["job_detail"]["jobPostingInfo"]
    return WellsFargoJobNormalizer().normalize(
        RawJobRecord(
            source_record_id=source_record_id,
            source_url=detail.get(
                "externalUrl",
                "https://wd1.myworkdaysite.com/recruiting/wf/WellsFargoJobs/job/Synthetic",
            ),
            retrieved_at=RETRIEVED_AT,
            payload=deepcopy(payload),
            provenance_metadata={"fixture": "persistence"},
        ),
        CollectionRequest(organization="Wells Fargo", run_id=RUN_ID),
    )


def persist(database: SQLiteDatabase, collected_jobs: list) -> int:
    return HiringPersistenceService(database.unit_of_work).save_collected_jobs(
        collected_jobs
    )


def test_database_initialization_creates_required_schema(tmp_path):
    database_path = tmp_path / "initialized.sqlite3"
    database = SQLiteDatabase(database_path)

    database.initialize()

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {"collection_runs", "evidence", "job_postings"} <= tables


def test_save_and_retrieve_evidence(database):
    evidence = make_evidence()
    with database.unit_of_work() as unit_of_work:
        unit_of_work.evidence.save(evidence)
        unit_of_work.commit()

    with database.unit_of_work() as unit_of_work:
        retrieved = unit_of_work.evidence.get(evidence.evidence_id)

    assert retrieved == evidence
    assert retrieved.provenance_metadata == evidence.provenance_metadata
    assert retrieved.retrieved_at == RETRIEVED_AT


def test_save_and_retrieve_job_posting_with_exact_evidence_link(database):
    evidence = make_evidence()
    posting = make_posting(evidence.evidence_id)
    with database.unit_of_work() as unit_of_work:
        unit_of_work.evidence.save(evidence)
        unit_of_work.job_postings.save(posting)
        unit_of_work.commit()

    with database.unit_of_work() as unit_of_work:
        retrieved = unit_of_work.job_postings.get(posting.job_id)
        linked_evidence = unit_of_work.evidence.get(retrieved.evidence_id)

    assert retrieved == posting
    assert linked_evidence == evidence
    assert retrieved.evidence_id == linked_evidence.evidence_id


def test_job_upsert_is_idempotent_by_organization_and_source_id(database):
    collected = normalize_wells_fargo(standard_us_full_time(), "R-100001")

    assert persist(database, [collected]) == 1
    assert persist(database, [collected]) == 1

    with database.unit_of_work() as unit_of_work:
        postings = unit_of_work.job_postings.list_all()
        evidence = unit_of_work.evidence.list_all()
    assert postings == [collected.posting]
    assert evidence == [collected.evidence]


def test_job_upsert_updates_source_record_but_preserves_database_identity(database):
    evidence = make_evidence()
    original = make_posting(evidence.evidence_id)
    from backend.app.application.hiring import CollectedJob

    persist(database, [CollectedJob(posting=original, evidence=evidence)])
    updated = original.model_copy(
        update={
            "job_id": uuid4(),
            "title": "Principal Platform Engineer",
            "description": "Updated public source description.",
            "location": "New York, NY",
        }
    )
    persist(database, [CollectedJob(posting=updated, evidence=evidence)])

    with database.unit_of_work() as unit_of_work:
        retrieved = unit_of_work.job_postings.get_by_source_identity(
            original.organization,
            original.source_job_id,
        )
        postings = unit_of_work.job_postings.list_all()

    assert len(postings) == 1
    assert retrieved.job_id == original.job_id
    assert retrieved.title == "Principal Platform Engineer"
    assert retrieved.description == "Updated public source description."
    assert retrieved.location == "New York, NY"


def test_multiple_wells_fargo_jobs_are_persisted(database):
    jobs = [
        normalize_wells_fargo(standard_us_full_time(), "R-100001"),
        normalize_wells_fargo(part_time(), "R-100002"),
    ]

    assert persist(database, jobs) == 2

    with database.unit_of_work() as unit_of_work:
        postings = unit_of_work.job_postings.list_all()
        evidence = unit_of_work.evidence.list_all()
    assert {posting.source_job_id for posting in postings} == {"R-100001", "R-100002"}
    assert len(evidence) == 2


def test_wells_fargo_normalized_collected_job_round_trips(database):
    collected = normalize_wells_fargo(standard_us_full_time(), "R-100001")
    persist(database, [collected])

    with database.unit_of_work() as unit_of_work:
        posting = unit_of_work.job_postings.get_by_source_identity(
            "Wells Fargo", "R-100001"
        )
        evidence = unit_of_work.evidence.get(posting.evidence_id)

    assert posting == collected.posting
    assert evidence == collected.evidence
    assert posting.evidence_id == evidence.evidence_id
    assert evidence.raw_reference == "workday:wf:WellsFargoJobs:R-100001"


def test_service_rolls_back_entire_batch_on_linkage_failure(database):
    valid = normalize_wells_fargo(standard_us_full_time(), "R-100001")
    invalid = normalize_wells_fargo(part_time(), "R-100002")
    invalid.posting.evidence_id = uuid4()

    with pytest.raises(ValueError, match="evidence_id must match"):
        persist(database, [valid, invalid])

    with database.unit_of_work() as unit_of_work:
        assert unit_of_work.job_postings.list_all() == []
        assert unit_of_work.evidence.list_all() == []


def test_temporary_databases_are_isolated(tmp_path):
    first = SQLiteDatabase(tmp_path / "first.sqlite3")
    second = SQLiteDatabase(tmp_path / "second.sqlite3")
    first.initialize()
    second.initialize()
    collected = normalize_wells_fargo(standard_us_full_time(), "R-100001")

    persist(first, [collected])

    with first.unit_of_work() as first_unit_of_work:
        assert len(first_unit_of_work.job_postings.list_all()) == 1
    with second.unit_of_work() as second_unit_of_work:
        assert second_unit_of_work.job_postings.list_all() == []
