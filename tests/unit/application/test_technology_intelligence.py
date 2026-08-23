from datetime import date, datetime, timezone
from uuid import uuid4

from backend.app.application.hiring import (
    EnrichmentField,
    EnrichmentFieldSupport,
    EnrichmentModelMetadata,
    EnrichmentSeniority,
    HiringEnrichmentResult,
)
from backend.app.application.technology import (
    TechnologyAnalyticsService,
    TechnologyCategory,
    TechnologyObservationService,
    categorize_technology,
    normalize_technology,
)
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence, SourceType


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


class FakeReadService:
    def __init__(self, jobs, evidence, enrichments):
        self.jobs = jobs
        self.evidence = evidence
        self.enrichments = enrichments

    def list_jobs_for_analytics(self, organization):
        return [job for job in self.jobs if job.organization == organization]

    def get_latest_enrichment(self, job_id):
        return self.enrichments.get(job_id)

    def get_evidence(self, evidence_id):
        return self.evidence.get(evidence_id)


def make_record(organization="Wells Fargo", technologies=None, *, enriched=True):
    evidence_id, job_id = uuid4(), uuid4()
    evidence = Evidence(
        evidence_id=evidence_id,
        source_url="https://example.test/job",
        source_type=SourceType.CAREER_SITE,
        retrieved_at=NOW,
        source_excerpt="Python, Power BI and SQL are required.",
        collector_identity="test",
    )
    job = JobPosting(
        job_id=job_id,
        organization=organization,
        source_job_id=str(job_id),
        title="Analytics Engineer",
        description="Python, Power BI and SQL are required.",
        location="Charlotte, NC",
        country="US",
        posted_date=date(2026, 8, 20),
        source_url="https://example.test/job",
        evidence_id=evidence_id,
    )
    enrichment = None
    if enriched:
        values = technologies or ["Python", "PowerBI", "SQL"]
        enrichment = HiringEnrichmentResult(
            job_id=job_id,
            evidence_id=evidence_id,
            technologies=values,
            seniority_level=EnrichmentSeniority.SENIOR,
            is_leadership=False,
            business_unit="Consumer Analytics",
            confidence=0.9,
            field_confidences={EnrichmentField.TECHNOLOGIES: 0.95},
            field_support=[EnrichmentFieldSupport(
                field=EnrichmentField.TECHNOLOGIES,
                value=value,
                excerpt=value,
                evidence_id=evidence_id,
            ) for value in values],
            model_metadata=EnrichmentModelMetadata(
                provider="vertex_gemini",
                model="gemini-2.5-flash",
                prompt_schema_version="hiring-enrichment-v3",
                enrichment_timestamp=NOW,
                model_confidence=0.85,
            ),
        )
    return job, evidence, enrichment


def build_service(records):
    jobs = [record[0] for record in records]
    evidence = {record[1].evidence_id: record[1] for record in records}
    enrichments = {record[0].job_id: record[2] for record in records if record[2]}
    return TechnologyAnalyticsService(
        TechnologyObservationService(FakeReadService(jobs, evidence, enrichments)),
        clock=lambda: NOW,
    )


def test_explicit_alias_normalization_and_conservative_unknown_handling():
    assert normalize_technology(" PowerBI ") == "Power BI"
    assert normalize_technology("MS Excel") == "Excel"
    assert normalize_technology("Structured Query Language") == "Structured Query Language"
    assert categorize_technology("Power BI") == TechnologyCategory.BI_VISUALIZATION
    assert categorize_technology("Unmapped Product") == TechnologyCategory.OTHER


def test_observations_include_source_support_and_preserve_traceability():
    enriched = make_record()
    plain = make_record(enriched=False)
    observations = build_service([enriched, plain]).observations("Wells Fargo")
    assert len(observations) == 6
    assert {item.job_id for item in observations} == {enriched[0].job_id, plain[0].job_id}
    assert all(item.support_references[0].evidence_id in {enriched[1].evidence_id, plain[1].evidence_id} for item in observations)
    assert all(item.support_classification == "multiple" for item in observations if item.job_id == enriched[0].job_id)
    assert all(item.support_classification == "source_evidence" for item in observations if item.job_id == plain[0].job_id)
    plain_python = next(item for item in observations if item.job_id == plain[0].job_id and item.normalized_technology == "Python")
    assert plain_python.provenance.provider == "deterministic_source"
    assert plain_python.source_field == "job.description"
    assert plain_python.matched_text == "Python"
    assert next(item for item in observations if item.job_id == plain[0].job_id).confidence == 1.0


def test_duplicate_aliases_are_one_observation_per_job():
    observations = build_service([make_record(technologies=["PowerBI", "Power BI"])]).observations("Wells Fargo")
    assert len(observations) == 3
    assert sum(item.normalized_technology == "Power BI" for item in observations) == 1


def test_analytics_uses_enriched_job_denominator_and_all_cross_tabs():
    records = [make_record(), make_record(enriched=False)]
    analytics = build_service(records).analytics("Wells Fargo")
    assert analytics.snapshot.total_jobs == 2
    assert analytics.snapshot.enriched_jobs == 1
    assert analytics.snapshot.technology_observation_count == 3
    assert analytics.snapshot.source_technology_jobs == 2
    assert analytics.snapshot.source_technology_observation_count == 6
    assert analytics.snapshot.unique_technologies == 3
    assert analytics.snapshot.technology_coverage_percentage == 50
    assert analytics.top_technologies[0].percentage_of_enriched_jobs == 100
    assert analytics.top_technologies[0].evidence_count == 1
    assert {item.category for item in analytics.categories} == {
        TechnologyCategory.PROGRAMMING_LANGUAGE,
        TechnologyCategory.BI_VISUALIZATION,
        TechnologyCategory.DATABASE,
    }
    assert len(analytics.business_unit_technologies) == 3
    assert len(analytics.geography_technologies) == 3
    assert len(analytics.seniority_technologies) == 3


def test_organization_isolation_empty_behavior_and_determinism():
    records = [make_record(), make_record("Other Bank")]
    service = build_service(records)
    first = service.analytics("Wells Fargo")
    second = service.analytics("Wells Fargo")
    empty = service.analytics("Unknown Bank")
    assert first == second
    assert first.snapshot.total_jobs == 1
    assert empty.snapshot.total_jobs == 0
    assert empty.top_technologies == []
