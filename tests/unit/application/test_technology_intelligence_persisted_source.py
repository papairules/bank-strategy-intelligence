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
    TechnologyObservationService,
)
from backend.app.application.technology.service import TechnologyObservationService as _TOS
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence, SourceType


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


class FakeReadService:
    def __init__(self, jobs, evidence, enrichments=None):
        self.jobs = jobs
        self.evidence = evidence
        self.enrichments = enrichments or {}

    def list_jobs_for_analytics(self, organization):
        return [job for job in self.jobs if job.organization == organization]

    def get_latest_enrichment(self, job_id):
        return self.enrichments.get(job_id)

    def get_evidence(self, evidence_id):
        return self.evidence.get(evidence_id)


def persisted_source_job(*, organization="BNY", technologies=None, business_unit=None):
    evidence_id, job_id = uuid4(), uuid4()
    evidence = Evidence(
        evidence_id=evidence_id,
        source_url="https://example.test/job",
        source_type=SourceType.CAREER_SITE,
        retrieved_at=NOW,
        source_excerpt="We use Apache Kafka and SQL for our data pipeline.",
        collector_identity="test",
    )
    job = JobPosting(
        job_id=job_id,
        organization=organization,
        source_job_id=str(job_id),
        title="Data Engineer",
        description="We use Apache Kafka and SQL for our data pipeline.",
        location="Pittsburgh, PA",
        country="US",
        posted_date=date(2026, 8, 20),
        source_url="https://example.test/job",
        evidence_id=evidence_id,
        technologies=["Kafka", "SQL"] if technologies is None else technologies,
        business_unit=business_unit,
    )
    return job, evidence


def enriched_job(*, organization="Wells Fargo", technologies=None):
    evidence_id, job_id = uuid4(), uuid4()
    evidence = Evidence(
        evidence_id=evidence_id,
        source_url="https://example.test/job",
        source_type=SourceType.CAREER_SITE,
        retrieved_at=NOW,
        source_excerpt="Python required.",
        collector_identity="test",
    )
    job = JobPosting(
        job_id=job_id,
        organization=organization,
        source_job_id=str(job_id),
        title="Analytics Engineer",
        description="Python required.",
        location="Charlotte, NC",
        country="US",
        posted_date=date(2026, 8, 20),
        source_url="https://example.test/job",
        evidence_id=evidence_id,
    )
    values = technologies or ["Python"]
    enrichment = HiringEnrichmentResult(
        job_id=job_id,
        evidence_id=evidence_id,
        technologies=values,
        seniority_level=EnrichmentSeniority.SENIOR,
        is_leadership=False,
        confidence=0.9,
        field_confidences={EnrichmentField.TECHNOLOGIES: 0.95},
        field_support=[
            EnrichmentFieldSupport(field=EnrichmentField.TECHNOLOGIES, value=value, excerpt=value, evidence_id=evidence_id)
            for value in values
        ],
        model_metadata=EnrichmentModelMetadata(
            provider="vertex_gemini",
            model="gemini-2.5-flash",
            prompt_schema_version="hiring-enrichment-v3",
            enrichment_timestamp=NOW,
            model_confidence=0.85,
        ),
    )
    return job, evidence, enrichment


def test_persisted_source_technologies_produce_observations_without_enrichment():
    job, evidence = persisted_source_job()
    service = TechnologyAnalyticsService(
        TechnologyObservationService(FakeReadService([job], {evidence.evidence_id: evidence})),
        clock=lambda: NOW,
    )

    observations = service.observations("BNY")

    assert {item.normalized_technology for item in observations} == {"Kafka", "SQL"}
    assert all(item.provenance.provider == _TOS.KEYWORD_MATCH_PROVIDER for item in observations)
    assert all(item.seniority == EnrichmentSeniority.UNKNOWN for item in observations)
    assert all(item.confidence == _TOS.KEYWORD_MATCH_CONFIDENCE for item in observations)


def test_persisted_source_observation_has_a_located_excerpt():
    job, evidence = persisted_source_job(technologies=["Kafka"])
    service = TechnologyAnalyticsService(
        TechnologyObservationService(FakeReadService([job], {evidence.evidence_id: evidence})),
        clock=lambda: NOW,
    )

    observations = service.observations("BNY")

    assert len(observations) == 1
    excerpt = observations[0].support_references[0].excerpt
    assert excerpt is not None and "Kafka" in excerpt


def test_snapshot_counts_persisted_source_jobs_separately_from_enriched():
    job, evidence = persisted_source_job()
    service = TechnologyAnalyticsService(
        TechnologyObservationService(FakeReadService([job], {evidence.evidence_id: evidence})),
        clock=lambda: NOW,
    )

    snapshot = service.analytics("BNY").snapshot

    assert snapshot.enriched_jobs == 0
    assert snapshot.jobs_with_technology_signal == 1
    assert snapshot.technology_signal_coverage_percentage == 100.0
    assert snapshot.technology_coverage_percentage == 0.0


def test_enrichment_and_persisted_source_do_not_double_count_the_same_technology():
    evidence_id, job_id = uuid4(), uuid4()
    evidence = Evidence(
        evidence_id=evidence_id,
        source_url="https://example.test/job",
        source_type=SourceType.CAREER_SITE,
        retrieved_at=NOW,
        source_excerpt="Kafka pipeline.",
        collector_identity="test",
    )
    job = JobPosting(
        job_id=job_id,
        organization="Wells Fargo",
        source_job_id=str(job_id),
        title="Data Engineer",
        description="Kafka pipeline.",
        location="Charlotte, NC",
        country="US",
        posted_date=date(2026, 8, 20),
        source_url="https://example.test/job",
        evidence_id=evidence_id,
        technologies=["Kafka"],
    )
    enrichment = HiringEnrichmentResult(
        job_id=job_id,
        evidence_id=evidence_id,
        technologies=["Kafka"],
        seniority_level=EnrichmentSeniority.SENIOR,
        is_leadership=False,
        confidence=0.9,
        model_metadata=EnrichmentModelMetadata(
            provider="vertex_gemini",
            model="gemini-2.5-flash",
            prompt_schema_version="hiring-enrichment-v3",
            enrichment_timestamp=NOW,
            model_confidence=0.85,
        ),
    )
    service = TechnologyAnalyticsService(
        TechnologyObservationService(
            FakeReadService([job], {evidence_id: evidence}, {job_id: enrichment})
        ),
        clock=lambda: NOW,
    )

    observations = service.observations("Wells Fargo")

    assert len(observations) == 1
    assert observations[0].provenance.provider == "vertex_gemini"


def test_jobs_with_technology_signal_counts_a_job_only_once_across_both_sources():
    enriched = enriched_job(organization="Wells Fargo", technologies=["Python", "Snowflake"])
    plain = persisted_source_job(organization="Wells Fargo", technologies=["Kafka"])
    unclassified_job, unclassified_evidence = persisted_source_job(
        organization="Wells Fargo", technologies=[]
    )
    jobs = [enriched[0], plain[0], unclassified_job]
    evidence = {enriched[1].evidence_id: enriched[1], plain[1].evidence_id: plain[1], unclassified_evidence.evidence_id: unclassified_evidence}
    enrichments = {enriched[0].job_id: enriched[2]}
    service = TechnologyAnalyticsService(
        TechnologyObservationService(FakeReadService(jobs, evidence, enrichments)),
        clock=lambda: NOW,
    )

    snapshot = service.analytics("Wells Fargo").snapshot

    assert snapshot.enriched_jobs == 1
    assert snapshot.jobs_with_technology_signal == 2
    assert snapshot.total_jobs == 3
