from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from backend.app.api.dependencies import get_hiring_read_service
from backend.app.application.hiring import (
    CollectedJob,
    EnrichmentField,
    EnrichmentFieldSupport,
    EnrichmentModelMetadata,
    EnrichmentSeniority,
    HiringEnrichmentPersistenceService,
    HiringEnrichmentResult,
    HiringPersistenceService,
    HiringReadService,
)
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence, SourceType
from backend.app.infrastructure.persistence.hiring import SQLiteDatabase
from backend.app.main import app


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


@pytest.fixture
def client(tmp_path):
    database = SQLiteDatabase(tmp_path / "technology-api.sqlite3")
    database.initialize()
    evidence_id, job_id = uuid4(), uuid4()
    evidence = Evidence(evidence_id=evidence_id, source_url="https://example.test/job", source_type=SourceType.CAREER_SITE, retrieved_at=NOW, source_excerpt="Python and Power BI", collector_identity="test")
    job = JobPosting(job_id=job_id, organization="Wells Fargo", source_job_id="R-1", title="Analytics Role", description="Python and Power BI", location="Charlotte, NC", country="US", posted_date=date(2026, 8, 20), source_url="https://example.test/job", evidence_id=evidence_id)
    HiringPersistenceService(database.unit_of_work).save_collected_jobs([CollectedJob(posting=job, evidence=evidence)])
    enrichment = HiringEnrichmentResult(
        job_id=job_id, evidence_id=evidence_id, technologies=["Python", "PowerBI"], seniority_level=EnrichmentSeniority.SENIOR, is_leadership=False, business_unit="Analytics", confidence=0.9,
        field_confidences={EnrichmentField.TECHNOLOGIES: 1.0},
        field_support=[EnrichmentFieldSupport(field=EnrichmentField.TECHNOLOGIES, value=value, excerpt=value, evidence_id=evidence_id) for value in ["Python", "PowerBI"]],
        model_metadata=EnrichmentModelMetadata(provider="vertex_gemini", model="gemini-2.5-flash", prompt_schema_version="hiring-enrichment-v3", enrichment_timestamp=NOW, model_confidence=0.85),
    )
    HiringEnrichmentPersistenceService(database.unit_of_work).save(enrichment)
    app.dependency_overrides[get_hiring_read_service] = lambda: HiringReadService(database.unit_of_work)
    with TestClient(app) as value:
        yield value
    app.dependency_overrides.clear()


def test_summary_and_analytics_serialize_coverage_and_traceability(client):
    summary = client.get("/api/v1/technology/organizations/Wells%20Fargo/summary")
    assert summary.status_code == 200
    assert summary.json()["snapshot"]["technology_observation_count"] == 2
    assert summary.json()["snapshot"]["technology_coverage_percentage"] == 100
    analytics = client.get("/api/v1/technology/organizations/Wells%20Fargo/analytics")
    assert analytics.status_code == 200
    assert analytics.json()["top_technologies"][0]["contributing_records"][0]["evidence_id"]


def test_observation_pagination_and_filters(client):
    page = client.get("/api/v1/technology/organizations/Wells%20Fargo/observations?limit=1&offset=1")
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert page.json()["returned_count"] == 1
    filtered = client.get("/api/v1/technology/organizations/Wells%20Fargo/observations?technology=power&category=BI%20%2F%20Visualization&business_unit=analytics&location=charlotte")
    assert filtered.status_code == 200
    assert filtered.json()["items"][0]["normalized_technology"] == "Power BI"
    assert filtered.json()["items"][0]["support_references"][0]["evidence_id"]


def test_empty_organization_and_query_validation(client):
    empty = client.get("/api/v1/technology/organizations/Other/analytics")
    assert empty.status_code == 200
    assert empty.json()["snapshot"]["total_jobs"] == 0
    assert client.get("/api/v1/technology/organizations/Wells%20Fargo/observations?limit=101").status_code == 422


def test_signals_endpoint_serializes_safe_low_coverage_state(client):
    response = client.get("/api/v1/technology/organizations/Wells%20Fargo/signals")
    assert response.status_code == 200
    body = response.json()
    assert body["organization"] == "Wells Fargo"
    assert body["generated_signal_count"] == 0
    assert body["signals"] == []
    assert body["enriched_jobs"] == 1
    assert body["limitations"]


def test_openapi_contains_technology_signals_path(client):
    assert "/api/v1/technology/organizations/{organization}/signals" in client.get("/openapi.json").json()["paths"]
