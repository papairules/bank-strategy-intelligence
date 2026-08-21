from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from backend.app.application.evidence import EvidenceRecordFilters, UnifiedEvidenceService
from backend.app.application.hiring import (
    EnrichmentModelMetadata,
    EnrichmentSeniority,
    HiringEnrichmentResult,
)
from backend.app.application.technology import TechnologyCategory
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence, SourceType


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


def make_job(organization="Wells Fargo", *, enriched=True):
    evidence_id, job_id = uuid4(), uuid4()
    evidence = Evidence(evidence_id=evidence_id, source_url="https://example.test/job", source_type=SourceType.CAREER_SITE, source_title="Analytics Role", retrieved_at=NOW, source_excerpt="Python analytics role", raw_reference="source:R-1", collector_identity="collector", provenance_metadata={"source_system": "Workday"})
    job = JobPosting(job_id=job_id, organization=organization, source_job_id=str(job_id), title="Analytics Role", description="Python analytics role", location="Charlotte, NC", country="US", posted_date=date(2026, 8, 20), source_url="https://example.test/job", evidence_id=evidence_id)
    enrichment = HiringEnrichmentResult(job_id=job_id, evidence_id=evidence_id, capability_classifications=["Data & Analytics"], skills=["analytics"], technologies=["Python"], seniority_level=EnrichmentSeniority.SENIOR, is_leadership=False, business_unit="Analytics", confidence=0.9, limitations=["Hiring evidence only."], model_metadata=EnrichmentModelMetadata(provider="vertex_gemini", model="gemini-2.5-flash", prompt_schema_version="hiring-enrichment-v3", enrichment_timestamp=NOW, model_confidence=0.85)) if enriched else None
    return job, evidence, enrichment


class FakeRead:
    def __init__(self, records):
        self.records = records
    def list_jobs_for_analytics(self, organization): return [r[0] for r in self.records if r[0].organization == organization]
    def list_all_jobs(self): return [r[0] for r in self.records]
    def get_evidence(self, evidence_id): return next((r[1] for r in self.records if r[1].evidence_id == evidence_id), None)
    def get_latest_enrichment(self, job_id): return next((r[2] for r in self.records if r[0].job_id == job_id), None)


class FakeHiringSignals:
    def __init__(self, evidence_id): self.evidence_id = evidence_id
    def generate(self, organization):
        signals = [] if organization != "Wells Fargo" else [SimpleNamespace(title="Observed hiring volume", signal=SimpleNamespace(signal_id=uuid4(), signal_type="hiring_volume", supporting_evidence_ids=[self.evidence_id, self.evidence_id]))]
        return SimpleNamespace(signals=signals, generated_at=NOW)


class FakeTechnologyObservations:
    def __init__(self, job, evidence): self.job, self.evidence = job, evidence
    def observations(self, organization):
        if organization != self.job.organization: return []
        support = SimpleNamespace(excerpt="Python")
        item = SimpleNamespace(job_id=self.job.job_id, evidence_id=self.evidence.evidence_id, normalized_technology="Python", category=TechnologyCategory.PROGRAMMING_LANGUAGE, confidence=1.0, support_references=[support])
        return [item, item]


class FakeTechnologySignals:
    def __init__(self, evidence_id): self.evidence_id = evidence_id
    def generate(self, organization):
        signal = SimpleNamespace(signal_id=uuid4(), signal_type=SimpleNamespace(value="technology_concentration"), title="Observed Python concentration", supporting_evidence_ids=[self.evidence_id, self.evidence_id])
        return SimpleNamespace(signals=[signal] if organization == "Wells Fargo" else [])


def service():
    enriched = make_job()
    plain = make_job(enriched=False)
    other = make_job("Other Bank")
    value = UnifiedEvidenceService(FakeRead([enriched, plain, other]), FakeHiringSignals(enriched[1].evidence_id), FakeTechnologyObservations(enriched[0], enriched[1]), FakeTechnologySignals(enriched[1].evidence_id))
    return value, enriched, plain


def test_summary_has_precise_coverage_source_and_relationship_metrics():
    value, _, _ = service()
    summary = value.summary("Wells Fargo")
    assert summary.total_evidence_records == 2
    assert summary.total_jobs == summary.jobs_with_evidence == 2
    assert summary.evidence_coverage == 100
    assert summary.enriched_evidence_count == 1
    assert summary.enrichment_coverage == 50
    assert summary.evidence_supporting_hiring_signals == 1
    assert summary.evidence_supporting_technology_observations == 1
    assert summary.evidence_supporting_technology_signals == 1
    assert summary.source_distribution[0].source == "Workday"


def test_records_separate_source_enrichment_and_derived_relationships():
    value, enriched, _ = service()
    record = value.list_records("Wells Fargo", EvidenceRecordFilters(enriched=True)).items[0]
    assert record.evidence_id == enriched[1].evidence_id
    assert record.enrichment_provider == "vertex_gemini"
    assert record.technologies == ["Python"]
    assert record.related_technology_observation_count == 1
    assert len(record.related_hiring_signals) == 1
    assert len(record.related_technology_signals) == 1
    assert record.evidence_preview == "Python analytics role"


def test_detail_is_traceable_and_deduplicates_signal_relationships():
    value, enriched, _ = service()
    detail = value.get(enriched[1].evidence_id)
    assert detail.job_id == enriched[0].job_id
    assert detail.raw_reference == "source:R-1"
    assert detail.enrichment_limitations == ["Hiring evidence only."]
    assert len(detail.related_hiring_signals) == 1
    assert len(detail.related_technology_signals) == 1
    assert len(detail.technology_observations) == 1


def test_filters_pagination_ordering_and_organization_isolation():
    value, enriched, plain = service()
    assert value.list_records("Wells Fargo", EvidenceRecordFilters(search="Python", limit=1)).total == 2
    assert value.list_records("Wells Fargo", EvidenceRecordFilters(technology="python")).total == 1
    assert value.list_records("Wells Fargo", EvidenceRecordFilters(capability="analytics")).total == 1
    assert value.list_records("Wells Fargo", EvidenceRecordFilters(location="charlotte")).total == 2
    assert value.list_records("Wells Fargo", EvidenceRecordFilters(job_id=plain[0].job_id)).total == 1
    page = value.list_records("Wells Fargo", EvidenceRecordFilters(limit=1, offset=1))
    assert page.returned_count == 1 and page.total == 2
    assert value.list_records("Other Bank", EvidenceRecordFilters()).total == 1
    assert value.list_records("Unknown", EvidenceRecordFilters()).items == []
    assert value.get(uuid4()) is None
