from datetime import date, datetime, timedelta, timezone
import importlib
import sqlite3
from uuid import NAMESPACE_URL, uuid4, uuid5

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_hiring_read_service
from backend.app.application.hiring import (
    CollectedJob,
    CollectionRun,
    CollectionStatus,
    HiringPersistenceService,
    HiringReadService,
)
from backend.app.domain.hiring import EmploymentType, JobPosting
from backend.app.domain.intelligence import Evidence, SourceType
from backend.app.infrastructure.persistence.hiring import SQLiteDatabase
from backend.app.main import app


BASE_TIME = datetime(2026, 8, 20, 12, 30, tzinfo=timezone.utc)


@pytest.fixture
def database(tmp_path) -> SQLiteDatabase:
    database = SQLiteDatabase(tmp_path / "api.sqlite3")
    database.initialize()
    return database


@pytest.fixture
def client(database):
    app.dependency_overrides[get_hiring_read_service] = lambda: HiringReadService(
        database.unit_of_work
    )
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def collected_job(
    source_job_id: str,
    *,
    organization: str = "Wells Fargo",
    country: str = "US",
    employment_type: EmploymentType = EmploymentType.FULL_TIME,
    posted_date: date = date(2026, 8, 20),
) -> CollectedJob:
    evidence_id = uuid5(NAMESPACE_URL, f"evidence:{organization}:{source_job_id}")
    source_url = f"https://careers.example.test/jobs/{source_job_id}"
    evidence = Evidence(
        evidence_id=evidence_id,
        source_url=source_url,
        source_type=SourceType.CAREER_SITE,
        source_title=f"Role {source_job_id}",
        retrieved_at=BASE_TIME,
        source_excerpt="Synthetic public job evidence.",
        raw_reference=f"workday:wf:WellsFargoJobs:{source_job_id}",
        collector_identity="api-test-collector",
        provenance_metadata={"source_system": "Workday", "page": 1},
    )
    posting = JobPosting(
        job_id=uuid5(NAMESPACE_URL, f"job:{organization}:{source_job_id}"),
        organization=organization,
        source_job_id=source_job_id,
        title=f"Role {source_job_id}",
        description="Synthetic normalized description, not a raw payload.",
        location="Charlotte, NC" if country == "US" else "Bengaluru, India",
        country=country,
        posted_date=posted_date,
        employment_type=employment_type,
        source_url=source_url,
        evidence_id=evidence_id,
    )
    return CollectedJob(posting=posting, evidence=evidence)


def persist_jobs(database: SQLiteDatabase, jobs: list[CollectedJob]) -> None:
    HiringPersistenceService(database.unit_of_work).save_collected_jobs(jobs)


def persist_run(
    database: SQLiteDatabase,
    *,
    organization: str,
    completed_offset: int,
) -> CollectionRun:
    collection_run = CollectionRun(
        run_id=uuid4(),
        collector_id="synthetic-collector",
        source_id="synthetic-source",
        organization=organization,
        started_at=BASE_TIME + timedelta(hours=completed_offset),
        completed_at=BASE_TIME + timedelta(hours=completed_offset, seconds=5),
        status=CollectionStatus.COMPLETED,
        pages_attempted=1,
        records_encountered=1,
        records_collected=1,
        records_skipped=0,
        issue_count=0,
        source_metadata={"pages": [{"offset": 0, "http_status": 200}]},
    )
    with database.unit_of_work() as unit_of_work:
        unit_of_work.collection_runs.save(collection_run)
        unit_of_work.commit()
    return collection_run


def test_empty_jobs_list_has_pagination_metadata(client):
    response = client.get("/api/v1/hiring/jobs")

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "limit": 25,
        "offset": 0,
        "returned_count": 0,
    }


def test_jobs_list_filters_and_does_not_expose_raw_payloads(client, database):
    jobs = [
        collected_job("R-1"),
        collected_job("R-2", employment_type=EmploymentType.PART_TIME),
        collected_job("R-3", country="IN"),
        collected_job("R-4", organization="Example Bank"),
    ]
    persist_jobs(database, jobs)

    all_response = client.get("/api/v1/hiring/jobs")
    organization_response = client.get(
        "/api/v1/hiring/jobs", params={"organization": "Example Bank"}
    )
    country_response = client.get(
        "/api/v1/hiring/jobs", params={"country": "IN"}
    )
    employment_response = client.get(
        "/api/v1/hiring/jobs", params={"employment_type": "part_time"}
    )

    assert all_response.status_code == 200
    assert all_response.json()["returned_count"] == 4
    assert organization_response.json()["items"][0]["source_job_id"] == "R-4"
    assert country_response.json()["items"][0]["source_job_id"] == "R-3"
    assert employment_response.json()["items"][0]["source_job_id"] == "R-2"
    serialized = str(all_response.json())
    assert "search_summary" not in serialized
    assert "job_detail" not in serialized
    assert "source_payload" not in serialized


def test_jobs_limit_offset_and_validation(client, database):
    persist_jobs(
        database,
        [
            collected_job("R-1", posted_date=date(2026, 8, 22)),
            collected_job("R-2", posted_date=date(2026, 8, 21)),
            collected_job("R-3", posted_date=date(2026, 8, 20)),
        ],
    )

    response = client.get(
        "/api/v1/hiring/jobs",
        params={"limit": 1, "offset": 1},
    )

    assert response.status_code == 200
    assert response.json()["limit"] == 1
    assert response.json()["offset"] == 1
    assert response.json()["returned_count"] == 1
    assert response.json()["items"][0]["source_job_id"] == "R-2"
    assert client.get("/api/v1/hiring/jobs", params={"limit": 101}).status_code == 422
    assert client.get("/api/v1/hiring/jobs", params={"offset": -1}).status_code == 422
    assert (
        client.get(
            "/api/v1/hiring/jobs",
            params={"employment_type": "invalid"},
        ).status_code
        == 422
    )


def test_job_detail_uuid_serialization_and_missing_404(client, database):
    collected = collected_job("R-1")
    persist_jobs(database, [collected])

    response = client.get(f"/api/v1/hiring/jobs/{collected.posting.job_id}")

    assert response.status_code == 200
    assert response.json()["job_id"] == str(collected.posting.job_id)
    assert response.json()["evidence_id"] == str(collected.evidence.evidence_id)
    assert client.get(f"/api/v1/hiring/jobs/{uuid4()}").status_code == 404
    assert client.get("/api/v1/hiring/jobs/not-a-uuid").status_code == 422


def test_job_evidence_uses_persisted_linkage_and_serializes_datetime(client, database):
    collected = collected_job("R-1")
    persist_jobs(database, [collected])

    response = client.get(
        f"/api/v1/hiring/jobs/{collected.posting.job_id}/evidence"
    )

    assert response.status_code == 200
    assert response.json()["evidence_id"] == str(collected.posting.evidence_id)
    assert response.json()["retrieved_at"] == "2026-08-20T12:30:00Z"
    assert response.json()["raw_reference"] == "workday:wf:WellsFargoJobs:R-1"
    assert client.get(f"/api/v1/hiring/jobs/{uuid4()}/evidence").status_code == 404


def test_missing_linked_evidence_returns_404(client, database):
    collected = collected_job("R-1")
    persist_jobs(database, [collected])
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            "DELETE FROM evidence WHERE evidence_id = ?",
            (str(collected.evidence.evidence_id),),
        )

    response = client.get(
        f"/api/v1/hiring/jobs/{collected.posting.job_id}/evidence"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Evidence not found."


def test_runs_list_filter_detail_and_datetime_serialization(client, database):
    first = persist_run(database, organization="Wells Fargo", completed_offset=0)
    second = persist_run(database, organization="Example Bank", completed_offset=1)
    third = persist_run(database, organization="Wells Fargo", completed_offset=2)

    response = client.get("/api/v1/hiring/runs", params={"limit": 2})
    filtered = client.get(
        "/api/v1/hiring/runs",
        params={"organization": "Wells Fargo"},
    )
    detail = client.get(f"/api/v1/hiring/runs/{second.run_id}")

    assert response.status_code == 200
    assert response.json()["returned_count"] == 2
    assert [item["run_id"] for item in response.json()["items"]] == [
        str(third.run_id),
        str(second.run_id),
    ]
    assert [item["run_id"] for item in filtered.json()["items"]] == [
        str(third.run_id),
        str(first.run_id),
    ]
    assert detail.status_code == 200
    assert detail.json()["run_id"] == str(second.run_id)
    assert detail.json()["started_at"] == "2026-08-20T13:30:00Z"
    assert client.get(f"/api/v1/hiring/runs/{uuid4()}").status_code == 404
    assert client.get("/api/v1/hiring/runs/not-a-uuid").status_code == 422
    assert client.get("/api/v1/hiring/runs", params={"limit": 101}).status_code == 422


def test_hiring_routes_appear_in_generated_openapi_schema(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {
        "/api/v1/hiring/jobs",
        "/api/v1/hiring/jobs/{job_id}",
        "/api/v1/hiring/jobs/{job_id}/evidence",
        "/api/v1/hiring/runs",
        "/api/v1/hiring/runs/{run_id}",
    } <= paths.keys()
    assert set(paths["/api/v1/hiring/jobs"]) == {"get"}


def test_application_import_starts_no_scheduler_and_makes_no_http_request(monkeypatch):
    import backend.app.main as main_module
    from backend.app.application.hiring import HiringCollectionScheduler

    http_calls = []
    scheduler_starts = []

    async def forbidden_request(*args, **kwargs):
        http_calls.append((args, kwargs))
        raise AssertionError("HTTP request made during import")

    def forbidden_start(self):
        scheduler_starts.append(self)
        raise AssertionError("scheduler started during import")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden_request)
    monkeypatch.setattr(HiringCollectionScheduler, "start", forbidden_start)

    importlib.reload(main_module)

    assert http_calls == []
    assert scheduler_starts == []
