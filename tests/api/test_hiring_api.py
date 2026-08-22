from datetime import date, datetime, timedelta, timezone
import importlib
from pathlib import Path
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
    EnrichmentField,
    EnrichmentFieldSupport,
    EnrichmentModelMetadata,
    EnrichmentSeniority,
    HiringCapability,
    HiringEnrichmentPersistenceService,
    HiringEnrichmentResult,
    HiringPersistenceService,
    HiringReadService,
    HiringTheme,
)
from backend.app.domain.hiring import EmploymentType, JobPosting, SeniorityLevel
from backend.app.domain.intelligence import Evidence, SourceType
from backend.app.config import HiringSettings
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
    location: str | None = None,
    capabilities: list[str] | None = None,
    seniority_level: SeniorityLevel | None = None,
    is_leadership: bool = False,
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
        location=location or ("Charlotte, NC" if country == "US" else "Bengaluru, India"),
        country=country,
        capability_classifications=capabilities or [],
        seniority_level=seniority_level,
        is_leadership=is_leadership,
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


def persist_enrichment(
    database: SQLiteDatabase,
    collected: CollectedJob,
    *,
    schema_version: str = "hiring-enrichment-v3",
    generated_at: datetime = BASE_TIME,
) -> HiringEnrichmentResult:
    enrichment = HiringEnrichmentResult(
        job_id=collected.posting.job_id,
        evidence_id=collected.evidence.evidence_id,
        capability_classifications=[HiringCapability.DATA_ANALYTICS],
        skills=["Analytics"],
        technologies=["Python"],
        seniority_level=EnrichmentSeniority.SENIOR,
        is_leadership=False,
        business_unit="Consumer Analytics",
        hiring_themes=[HiringTheme.DATA_MODERNIZATION],
        confidence=0.9,
        field_confidences={EnrichmentField.TECHNOLOGIES: 1.0},
        field_support=[
            EnrichmentFieldSupport(
                field=EnrichmentField.TECHNOLOGIES,
                value="Python",
                excerpt="Python",
                evidence_id=collected.evidence.evidence_id,
            )
        ],
        limitations=["Synthetic offline enrichment."],
        model_metadata=EnrichmentModelMetadata(
            provider="vertex_gemini",
            model="gemini-2.5-flash",
            prompt_schema_version=schema_version,
            enrichment_timestamp=generated_at,
            model_confidence=0.85,
        ),
    )
    HiringEnrichmentPersistenceService(database.unit_of_work).save(enrichment)
    return enrichment


def test_empty_jobs_list_has_pagination_metadata(client):
    response = client.get(
        "/api/v1/hiring/jobs",
        params={"organization": "Wells Fargo"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "total": 0,
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

    wells_fargo_response = client.get(
        "/api/v1/hiring/jobs", params={"organization": "Wells Fargo"}
    )
    organization_response = client.get(
        "/api/v1/hiring/jobs", params={"organization": "Example Bank"}
    )
    country_response = client.get(
        "/api/v1/hiring/jobs", params={"organization": "Wells Fargo", "country": "IN"}
    )
    employment_response = client.get(
        "/api/v1/hiring/jobs", params={"organization": "Wells Fargo", "employment_type": "part_time"}
    )

    assert wells_fargo_response.status_code == 200
    assert wells_fargo_response.json()["returned_count"] == 3
    assert organization_response.json()["items"][0]["source_job_id"] == "R-4"
    assert country_response.json()["items"][0]["source_job_id"] == "R-3"
    assert employment_response.json()["items"][0]["source_job_id"] == "R-2"
    serialized = str(wells_fargo_response.json())
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
        params={"organization": "Wells Fargo", "limit": 1, "offset": 1},
    )

    assert response.status_code == 200
    assert response.json()["limit"] == 1
    assert response.json()["offset"] == 1
    assert response.json()["returned_count"] == 1
    assert response.json()["items"][0]["source_job_id"] == "R-2"
    assert client.get("/api/v1/hiring/jobs", params={"organization": "Wells Fargo", "limit": 101}).status_code == 422
    assert client.get("/api/v1/hiring/jobs", params={"organization": "Wells Fargo", "offset": -1}).status_code == 422
    assert client.get("/api/v1/hiring/jobs").status_code == 422
    assert (
        client.get(
            "/api/v1/hiring/jobs",
            params={"organization": "Wells Fargo", "employment_type": "invalid"},
        ).status_code
        == 422
    )


def test_job_detail_uuid_serialization_and_missing_404(client, database):
    collected = collected_job("R-1")
    persist_jobs(database, [collected])

    response = client.get(
        f"/api/v1/hiring/jobs/{collected.posting.job_id}",
        params={"organization": "Wells Fargo"},
    )

    assert response.status_code == 200
    assert response.json()["job"]["job_id"] == str(collected.posting.job_id)
    assert response.json()["evidence"]["evidence_id"] == str(
        collected.evidence.evidence_id
    )
    assert response.json()["enrichment"] is None
    assert client.get(f"/api/v1/hiring/jobs/{uuid4()}", params={"organization": "Wells Fargo"}).status_code == 404
    assert client.get("/api/v1/hiring/jobs/not-a-uuid", params={"organization": "Wells Fargo"}).status_code == 422
    assert client.get(f"/api/v1/hiring/jobs/{collected.posting.job_id}", params={"organization": "Other Bank"}).status_code == 404


def test_job_evidence_uses_persisted_linkage_and_serializes_datetime(client, database):
    collected = collected_job("R-1")
    persist_jobs(database, [collected])

    response = client.get(
        f"/api/v1/hiring/jobs/{collected.posting.job_id}/evidence",
        params={"organization": "Wells Fargo"},
    )

    assert response.status_code == 200
    assert response.json()["evidence_id"] == str(collected.posting.evidence_id)
    assert response.json()["retrieved_at"] == "2026-08-20T12:30:00Z"
    assert response.json()["raw_reference"] == "workday:wf:WellsFargoJobs:R-1"
    assert client.get(f"/api/v1/hiring/jobs/{uuid4()}/evidence", params={"organization": "Wells Fargo"}).status_code == 404


def test_missing_linked_evidence_returns_404(client, database):
    collected = collected_job("R-1")
    persist_jobs(database, [collected])
    with sqlite3.connect(database.path) as connection:
        connection.execute(
            "DELETE FROM evidence WHERE evidence_id = ?",
            (str(collected.evidence.evidence_id),),
        )

    response = client.get(
        f"/api/v1/hiring/jobs/{collected.posting.job_id}/evidence",
        params={"organization": "Wells Fargo"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Evidence not found."


def test_runs_list_filter_detail_and_datetime_serialization(client, database):
    first = persist_run(database, organization="Wells Fargo", completed_offset=0)
    second = persist_run(database, organization="Example Bank", completed_offset=1)
    third = persist_run(database, organization="Wells Fargo", completed_offset=2)

    response = client.get(
        "/api/v1/hiring/runs",
        params={"organization": "Wells Fargo", "limit": 2},
    )
    filtered = client.get(
        "/api/v1/hiring/runs",
        params={"organization": "Wells Fargo"},
    )
    detail = client.get(
        f"/api/v1/hiring/runs/{second.run_id}",
        params={"organization": "Example Bank"},
    )

    assert response.status_code == 200
    assert response.json()["returned_count"] == 2
    assert [item["run_id"] for item in response.json()["items"]] == [
        str(third.run_id),
        str(first.run_id),
    ]
    assert [item["run_id"] for item in filtered.json()["items"]] == [
        str(third.run_id),
        str(first.run_id),
    ]
    assert detail.status_code == 200
    assert detail.json()["run_id"] == str(second.run_id)
    assert detail.json()["started_at"] == "2026-08-20T13:30:00Z"
    assert client.get(f"/api/v1/hiring/runs/{uuid4()}", params={"organization": "Wells Fargo"}).status_code == 404
    assert client.get("/api/v1/hiring/runs/not-a-uuid", params={"organization": "Wells Fargo"}).status_code == 422
    assert client.get("/api/v1/hiring/runs", params={"organization": "Wells Fargo", "limit": 101}).status_code == 422
    assert client.get(f"/api/v1/hiring/runs/{second.run_id}", params={"organization": "Wells Fargo"}).status_code == 404


def test_organization_summary_and_unknown_organization(client, database):
    jobs = [
        collected_job(
            f"R-{index}",
            capabilities=["Data & Analytics"],
            seniority_level=SeniorityLevel.SENIOR,
            posted_date=date(2026, 8, 15 + index),
        )
        for index in range(1, 6)
    ]
    persist_jobs(database, jobs)
    persist_enrichment(database, jobs[0])
    latest_run = persist_run(database, organization="Wells Fargo", completed_offset=2)

    response = client.get(
        "/api/v1/hiring/organizations/Wells%20Fargo/summary"
    )
    unknown = client.get("/api/v1/hiring/organizations/Unknown%20Bank/summary")

    assert response.status_code == 200
    body = response.json()
    assert body["organization"] == "Wells Fargo"
    assert body["total_observed_jobs"] == 5
    assert body["jobs_with_evidence"] == 5
    assert body["evidence_coverage"] == 100.0
    assert body["enriched_job_count"] == 1
    assert body["enrichment_coverage"] == 20.0
    assert body["latest_collection_run"]["run_id"] == str(latest_run.run_id)
    assert body["signal_count"] > 0
    assert body["geographic"]["by_city"][0]["value"] == "Charlotte"
    assert body["capability"]["capabilities"][0]["capability"] == "Data & Analytics"
    assert unknown.status_code == 200
    assert unknown.json()["total_observed_jobs"] == 0
    assert unknown.json()["latest_collection_run"] is None


def test_organization_jobs_pagination_filters_and_isolation(client, database):
    jobs = [
        collected_job(
            "R-1",
            location="Charlotte, NC",
            capabilities=["Data & Analytics"],
            seniority_level=SeniorityLevel.SENIOR,
            posted_date=date(2026, 8, 22),
        ),
        collected_job(
            "R-2",
            location="New York, NY",
            capabilities=["Risk & Compliance"],
            seniority_level=SeniorityLevel.MANAGER,
            posted_date=date(2026, 8, 21),
        ),
        collected_job("R-3", organization="Other Bank"),
    ]
    persist_jobs(database, jobs)

    page = client.get(
        "/api/v1/hiring/organizations/Wells%20Fargo/jobs",
        params={"limit": 1, "offset": 1},
    )
    location = client.get(
        "/api/v1/hiring/organizations/Wells%20Fargo/jobs",
        params={"location": "Charlotte"},
    )
    capability = client.get(
        "/api/v1/hiring/organizations/Wells%20Fargo/jobs",
        params={"capability": "Risk & Compliance"},
    )
    seniority = client.get(
        "/api/v1/hiring/organizations/Wells%20Fargo/jobs",
        params={"seniority": "senior"},
    )

    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert page.json()["returned_count"] == 1
    assert page.json()["items"][0]["source_job_id"] == "R-2"
    assert location.json()["items"][0]["source_job_id"] == "R-1"
    assert capability.json()["items"][0]["source_job_id"] == "R-2"
    assert seniority.json()["items"][0]["source_job_id"] == "R-1"
    assert (
        client.get(
            "/api/v1/hiring/organizations/Wells%20Fargo/jobs",
            params={"limit": 101},
        ).status_code
        == 422
    )


def test_job_detail_latest_enrichment_and_history(client, database):
    collected = collected_job("R-1")
    persist_jobs(database, [collected])
    older = persist_enrichment(database, collected)
    newer = persist_enrichment(
        database,
        collected,
        schema_version="hiring-enrichment-v4",
        generated_at=BASE_TIME + timedelta(minutes=1),
    )

    detail = client.get(f"/api/v1/hiring/jobs/{collected.posting.job_id}", params={"organization": "Wells Fargo"})
    latest = client.get(
        f"/api/v1/hiring/jobs/{collected.posting.job_id}/enrichment",
        params={"organization": "Wells Fargo"},
    )
    history = client.get(
        f"/api/v1/hiring/jobs/{collected.posting.job_id}/enrichments",
        params={"organization": "Wells Fargo"},
    )

    assert detail.status_code == 200
    assert detail.json()["enrichment"]["model_metadata"][
        "prompt_schema_version"
    ] == "hiring-enrichment-v4"
    assert latest.status_code == 200
    assert latest.json()["job_id"] == str(newer.job_id)
    assert latest.json()["confidence"] == 0.9
    assert latest.json()["model_metadata"]["enrichment_timestamp"] == (
        "2026-08-20T12:31:00Z"
    )
    assert history.status_code == 200
    assert history.json()["returned_count"] == 2
    assert [
        item["model_metadata"]["prompt_schema_version"]
        for item in history.json()["items"]
    ] == ["hiring-enrichment-v4", "hiring-enrichment-v3"]
    assert older.evidence_id == newer.evidence_id


def test_missing_enrichment_returns_404_without_generation(client, database):
    collected = collected_job("R-1")
    persist_jobs(database, [collected])

    response = client.get(
        f"/api/v1/hiring/jobs/{collected.posting.job_id}/enrichment",
        params={"organization": "Wells Fargo"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Hiring enrichment not found."


def test_analytics_and_signals_are_deterministic_and_organization_scoped(
    client,
    database,
):
    jobs = [
        collected_job(
            f"R-{index}",
            capabilities=["Data & Analytics"],
            seniority_level=SeniorityLevel.SENIOR,
            posted_date=date(2026, 7, 1) + timedelta(days=index * 7),
        )
        for index in range(1, 6)
    ]
    persist_jobs(database, [*jobs, collected_job("OTHER", organization="Other Bank")])

    analytics = client.get(
        "/api/v1/hiring/organizations/Wells%20Fargo/analytics"
    )
    signals = client.get("/api/v1/hiring/organizations/Wells%20Fargo/signals")

    assert analytics.status_code == 200
    assert analytics.json()["snapshot"]["total_active_jobs"] == 5
    assert analytics.json()["geographic"]["total_jobs"] == 5
    assert len(analytics.json()["weekly_trend"]["buckets"]) == 5
    assert signals.status_code == 200
    assert signals.json()["returned_count"] > 0
    serialized = str(signals.json()).lower()
    assert "consulting opportunity" not in serialized
    assert "recommendation" not in serialized


def test_organization_collection_runs_are_scoped(client, database):
    wells_fargo = persist_run(
        database,
        organization="Wells Fargo",
        completed_offset=0,
    )
    persist_run(database, organization="Other Bank", completed_offset=1)

    response = client.get(
        "/api/v1/hiring/organizations/Wells%20Fargo/collection-runs"
    )

    assert response.status_code == 200
    assert response.json()["returned_count"] == 1
    assert response.json()["items"][0]["run_id"] == str(wells_fargo.run_id)
    assert "source_metadata" in response.json()["items"][0]


def test_hiring_routes_appear_in_generated_openapi_schema(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {
        "/api/v1/hiring/jobs",
        "/api/v1/hiring/jobs/{job_id}",
        "/api/v1/hiring/jobs/{job_id}/evidence",
        "/api/v1/hiring/runs",
        "/api/v1/hiring/runs/{run_id}",
        "/api/v1/hiring/organizations/{organization}/summary",
        "/api/v1/hiring/organizations/{organization}/jobs",
        "/api/v1/hiring/organizations/{organization}/analytics",
        "/api/v1/hiring/organizations/{organization}/signals",
        "/api/v1/hiring/organizations/{organization}/collection-runs",
        "/api/v1/hiring/jobs/{job_id}/enrichment",
        "/api/v1/hiring/jobs/{job_id}/enrichments",
    } <= paths.keys()
    assert set(paths["/api/v1/hiring/jobs"]) == {"get"}


def test_cors_defaults_and_preflight_are_conservative(client, monkeypatch):
    response = client.options(
        "/api/v1/hiring/jobs",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
    defaults = HiringSettings(_env_file=None)
    assert "http://127.0.0.1:5173" in defaults.cors_origins
    assert "*" not in defaults.cors_origins
    monkeypatch.setenv("BSI_CORS_ORIGINS", '["http://localhost:4173"]')
    assert HiringSettings(_env_file=None).cors_origins == ["http://localhost:4173"]


def test_api_layer_has_no_source_provider_or_sqlite_coupling():
    api_root = Path("backend/app/api")
    source = "\n".join(
        path.read_text()
        for path in api_root.rglob("*.py")
    )

    assert "WellsFargo" not in source
    assert "Workday" not in source
    assert "google.genai" not in source
    assert "VertexGemini" not in source
    assert "import sqlite3" not in source


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
