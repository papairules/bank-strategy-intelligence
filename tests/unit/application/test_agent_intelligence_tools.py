from datetime import date, datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.app.application.agents import (
    AgentToolRegistry,
    CollectionContextInput,
    EvidenceIdInput,
    EvidenceSearchInput,
    JobIdInput,
    JobSearchInput,
    OrganizationInput,
    TechnologyObservationSearchInput,
)
from backend.app.application.hiring import (
    CollectionRun,
    CollectionStatus,
    EnrichmentField,
    EnrichmentFieldSupport,
    EnrichmentModelMetadata,
    EnrichmentSeniority,
    HiringCapability,
    HiringEnrichmentPersistenceService,
    HiringEnrichmentResult,
    HiringTheme,
)
from backend.app.config import HiringSettings
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence, SourceType
from backend.app.infrastructure.composition.agent_tools import create_agent_intelligence_tools
from backend.app.infrastructure.persistence.hiring import SQLiteDatabase


NOW = datetime(2026, 8, 21, 12, tzinfo=timezone.utc)


@pytest.fixture
def tool_fixture(tmp_path):
    path = tmp_path / "agent-tools.sqlite3"
    database = SQLiteDatabase(path)
    database.initialize()
    records = []
    for index, organization in enumerate(("Example Bank", "Other Bank")):
        evidence = Evidence(evidence_id=uuid4(), source_url=f"https://example.test/{index}", source_type=SourceType.CAREER_SITE, source_title="Analytics Role", retrieved_at=NOW, source_excerpt="Python and SQL analytics role.", raw_reference=f"source:R-{index}", collector_identity="test", provenance_metadata={"source_system": "Career Site"})
        job = JobPosting(job_id=uuid4(), organization=organization, source_job_id=f"R-{index}", title="Analytics Role", description="Python and SQL analytics role.", location="Charlotte, NC", country="US", posted_date=date(2026, 8, 20), source_url=f"https://example.test/{index}", evidence_id=evidence.evidence_id)
        with database.unit_of_work() as unit:
            unit.evidence.save(evidence)
            unit.job_postings.save(job)
            unit.commit()
        records.append((job, evidence))
    job, evidence = records[0]
    enrichment = HiringEnrichmentResult(job_id=job.job_id, evidence_id=evidence.evidence_id, capability_classifications=[HiringCapability.DATA_ANALYTICS], skills=["analytics"], technologies=["Python", "SQL"], seniority_level=EnrichmentSeniority.SENIOR, is_leadership=False, business_unit="Analytics", hiring_themes=[HiringTheme.DATA_MODERNIZATION], confidence=0.9, field_confidences={EnrichmentField.TECHNOLOGIES: 1.0}, field_support=[EnrichmentFieldSupport(field=EnrichmentField.TECHNOLOGIES, value=value, excerpt=value, evidence_id=evidence.evidence_id) for value in ("Python", "SQL")], limitations=["Evidence-limited classification."], model_metadata=EnrichmentModelMetadata(provider="vertex_gemini", model="gemini-2.5-flash", prompt_schema_version="hiring-enrichment-v3", enrichment_timestamp=NOW, model_confidence=0.85))
    HiringEnrichmentPersistenceService(database.unit_of_work).save(enrichment)
    run = CollectionRun(run_id=uuid4(), collector_id="test", source_id="career-site", organization="Example Bank", started_at=NOW, completed_at=NOW, status=CollectionStatus.COMPLETED, pages_attempted=1, records_encountered=1, records_collected=1, records_skipped=0, issue_count=0)
    with database.unit_of_work() as unit:
        unit.collection_runs.save(run)
        unit.commit()
    settings = HiringSettings(sqlite_database_path=path)
    return create_agent_intelligence_tools(settings), records


def test_hiring_tools_summary_search_job_signals_and_collection(tool_fixture):
    tools, records = tool_fixture
    organization = OrganizationInput(organization="Example Bank")
    summary = tools.hiring.get_summary(organization)
    assert summary.total_observed_jobs == 1
    search = tools.hiring.search_jobs(JobSearchInput(organization="Example Bank", location="Charlotte", limit=1))
    assert search.total == 1 and search.items[0].job_id == records[0][0].job_id
    intelligence = tools.hiring.get_job_intelligence(JobIdInput(job_id=records[0][0].job_id))
    assert intelligence.found and intelligence.enrichment.available
    assert intelligence.enrichment.technologies == ["Python", "SQL"]
    assert tools.hiring.get_job_intelligence(JobIdInput(job_id=uuid4())).found is False
    assert tools.hiring.get_signals(organization).signals == []
    context = tools.hiring.get_collection_context(CollectionContextInput(organization="Example Bank"))
    assert context.returned_count == 1 and context.latest_status == "completed"


def test_technology_tools_summary_analytics_observations_and_suppression(tool_fixture):
    tools, records = tool_fixture
    organization = OrganizationInput(organization="Example Bank")
    summary = tools.technology.get_summary(organization)
    assert summary.enriched_jobs == 1
    assert summary.technology_observation_count == 2
    assert summary.technology_coverage == 1
    assert tools.technology.get_analytics(organization).analytics.snapshot.total_jobs == 1
    observations = tools.technology.search_observations(TechnologyObservationSearchInput(organization="Example Bank", technology="python", limit=1))
    assert observations.total == 1 and observations.items[0].evidence_id == records[0][1].evidence_id
    signals = tools.technology.get_signals(organization)
    assert signals.signals == [] and signals.limitations


def test_evidence_tools_summary_search_detail_and_trace(tool_fixture):
    tools, records = tool_fixture
    organization = OrganizationInput(organization="Example Bank")
    summary = tools.evidence.get_summary(organization)
    assert summary.total_evidence_records == 1
    search = tools.evidence.search(EvidenceSearchInput(organization="Example Bank", enriched=True, technology="Python"))
    assert search.total == 1
    evidence_id = records[0][1].evidence_id
    detail = tools.evidence.get(EvidenceIdInput(evidence_id=evidence_id))
    assert detail.found and detail.detail.enrichment_present
    trace = tools.evidence.trace(EvidenceIdInput(evidence_id=evidence_id))
    assert trace.found and trace.job_id == records[0][0].job_id
    assert trace.technology_observations == ["Python", "SQL"]
    assert trace.cross_domain_signal_ids == []
    assert tools.evidence.trace(EvidenceIdInput(evidence_id=uuid4())).found is False


def test_strategy_tools_return_context_and_explicit_suppression(tool_fixture):
    tools, _ = tool_fixture
    organization = OrganizationInput(organization="Example Bank")
    context = tools.strategy.get_context(organization)
    assert context.hiring_coverage == 1
    assert context.enrichment_coverage == 1
    assert context.technology_observation_count == 2
    assert context.cross_domain_signal_count == 0
    signals = tools.strategy.get_signals(organization)
    assert signals.signals == [] and signals.limitations


def test_organization_isolation_and_unavailable_context(tool_fixture):
    tools, _ = tool_fixture
    other = tools.hiring.search_jobs(JobSearchInput(organization="Other Bank"))
    assert other.total == 1
    missing = tools.hiring.search_jobs(JobSearchInput(organization="Missing Bank"))
    assert missing.items == [] and missing.total == 0
    assert tools.technology.get_summary(OrganizationInput(organization="Missing Bank")).technology_observation_count == 0
    assert tools.evidence.get_summary(OrganizationInput(organization="Missing Bank")).total_evidence_records == 0


def test_pagination_is_bounded_and_search_order_is_deterministic(tool_fixture):
    tools, _ = tool_fixture
    with pytest.raises(ValidationError):
        JobSearchInput(organization="Example Bank", limit=51)
    with pytest.raises(ValidationError):
        EvidenceSearchInput(organization="Example Bank", limit=0)
    first = tools.technology.search_observations(TechnologyObservationSearchInput(organization="Example Bank"))
    second = tools.technology.search_observations(TechnologyObservationSearchInput(organization="Example Bank"))
    assert first == second


def test_registry_is_complete_unique_typed_and_read_only():
    definitions = AgentToolRegistry().list()
    assert len(definitions) == 15
    names = [item.name for item in definitions]
    assert len(names) == len(set(names))
    assert all(item.read_only for item in definitions)
    assert all(item.name.startswith(f"{item.domain.value}.") for item in definitions)
    assert all(item.input_model.model_fields is not None for item in definitions)
    assert all(item.output_model.model_fields is not None for item in definitions)
    assert {item.domain.value for item in definitions} == {"hiring", "technology", "evidence", "strategy"}


def test_agent_application_layer_has_no_forbidden_imports():
    root = Path("backend/app/application/agents")
    content = "\n".join(path.read_text() for path in root.glob("*.py")).casefold()
    for forbidden in ("sqlite", "fastapi", "google.genai", "vertex", "workday", "wells_fargo", "httpx", "requests"):
        assert forbidden not in content
