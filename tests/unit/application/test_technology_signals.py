from datetime import date, datetime, timezone
from uuid import uuid4

from backend.app.application.technology import (
    BusinessUnitTechnologyAggregate,
    GeographyTechnologyAggregate,
    TechnologyAnalyticsResult,
    TechnologyCategory,
    TechnologyCategoryAggregate,
    TechnologyIntelligenceSnapshot,
    TechnologyRecordReference,
    TechnologySignalService,
    TechnologySignalThresholds,
    TechnologySignalType,
    TopTechnologyAggregate,
)


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


class FakeAnalytics:
    def __init__(self, result):
        self.result = result

    def analytics(self, organization):
        if organization == self.result.snapshot.organization:
            return self.result
        return make_analytics(organization=organization, total_jobs=0, enriched_jobs=0, job_count=0)


def references(count):
    return [TechnologyRecordReference(job_id=uuid4(), evidence_id=uuid4()) for _ in range(count)]


def make_analytics(*, organization="Wells Fargo", total_jobs=10, enriched_jobs=5, job_count=3, duplicate=False):
    refs = references(job_count)
    aggregate_refs = refs + ([refs[0]] if duplicate and refs else [])
    observations = max(enriched_jobs * 2, 0)
    snapshot = TechnologyIntelligenceSnapshot(
        organization=organization,
        total_jobs=total_jobs,
        enriched_jobs=enriched_jobs,
        technology_observation_count=observations,
        unique_technologies=2 if job_count else 0,
        technology_coverage_percentage=(enriched_jobs / total_jobs * 100 if total_jobs else 0),
        jobs_with_technology_signal=enriched_jobs,
        technology_signal_coverage_percentage=(enriched_jobs / total_jobs * 100 if total_jobs else 0),
        observation_start=date(2026, 7, 1) if total_jobs else None,
        observation_end=date(2026, 8, 20) if total_jobs else None,
        generated_at=NOW,
    )
    if not job_count:
        return TechnologyAnalyticsResult(snapshot=snapshot, top_technologies=[], categories=[], business_unit_technologies=[], geography_technologies=[], seniority_technologies=[])
    return TechnologyAnalyticsResult(
        snapshot=snapshot,
        top_technologies=[TopTechnologyAggregate(technology="Python", category=TechnologyCategory.PROGRAMMING_LANGUAGE, job_count=job_count, observation_count=job_count, percentage_of_enriched_jobs=job_count / enriched_jobs * 100, percentage_of_technology_classified_jobs=job_count / enriched_jobs * 100, evidence_count=job_count, contributing_records=aggregate_refs)],
        categories=[TechnologyCategoryAggregate(category=TechnologyCategory.PROGRAMMING_LANGUAGE, unique_technology_count=3, observation_count=max(5, job_count), job_count=job_count, contributing_records=aggregate_refs)],
        business_unit_technologies=[BusinessUnitTechnologyAggregate(business_unit="Analytics", technology="Python", job_count=job_count, contributing_records=aggregate_refs)],
        geography_technologies=[GeographyTechnologyAggregate(location="Charlotte, NC", technology="Python", job_count=job_count, contributing_records=aggregate_refs)],
        seniority_technologies=[],
    )


def test_low_coverage_and_empty_data_suppress_signals_with_limitations():
    low = TechnologySignalService(FakeAnalytics(make_analytics(total_jobs=19, enriched_jobs=1, job_count=1))).generate("Wells Fargo")
    assert low.signals == []
    assert low.enrichment_coverage == 1 / 19
    assert any("coverage" in item.lower() for item in low.limitations)
    empty = TechnologySignalService(FakeAnalytics(make_analytics(total_jobs=0, enriched_jobs=0, job_count=0))).generate("Wells Fargo")
    assert empty.signals == []


def test_sufficient_data_generates_supported_signal_types_with_cautious_language():
    result = TechnologySignalService(FakeAnalytics(make_analytics())).generate("Wells Fargo")
    types = {signal.signal_type for signal in result.signals}
    assert TechnologySignalType.TECHNOLOGY_CONCENTRATION in types
    assert TechnologySignalType.TECHNOLOGY_CATEGORY_CONCENTRATION in types
    assert TechnologySignalType.BUSINESS_UNIT_TECHNOLOGY_CONCENTRATION in types
    assert TechnologySignalType.GEOGRAPHIC_TECHNOLOGY_CONCENTRATION in types
    assert TechnologySignalType.TECHNOLOGY_HIRING_CLUSTER in types
    assert all("strategy is" not in signal.summary.lower() for signal in result.signals)
    assert all("currently enriched hiring" in signal.summary.lower() for signal in result.signals)


def test_scores_ids_and_traceability_are_bounded_deterministic_and_deduplicated():
    analytics = make_analytics(duplicate=True)
    service = TechnologySignalService(FakeAnalytics(analytics))
    first = service.generate("Wells Fargo")
    second = service.generate("Wells Fargo")
    assert first == second
    for signal in first.signals:
        assert 0 <= signal.confidence <= 1
        assert 0 <= signal.strength <= 1
        assert 0 <= signal.evidence_coverage <= 1
        assert len(signal.supporting_job_ids) == len(set(signal.supporting_job_ids))
        assert len(signal.supporting_evidence_ids) == len(set(signal.supporting_evidence_ids))
        assert set(signal.supporting_evidence_ids).issubset({item.evidence_id for item in analytics.top_technologies[0].contributing_records})


def test_threshold_boundaries_and_missing_classifications():
    analytics = make_analytics()
    strict = TechnologySignalThresholds(minimum_enrichment_coverage=0.51)
    assert TechnologySignalService(FakeAnalytics(analytics), strict).generate("Wells Fargo").signals == []
    at_boundary = TechnologySignalThresholds(minimum_enrichment_coverage=0.5)
    assert TechnologySignalService(FakeAnalytics(analytics), at_boundary).generate("Wells Fargo").signals
    missing = analytics.model_copy(update={"top_technologies": [], "categories": [], "business_unit_technologies": [], "geography_technologies": []})
    assert TechnologySignalService(FakeAnalytics(missing)).generate("Wells Fargo").signals == []


def test_organization_isolation_and_relevant_limitations():
    service = TechnologySignalService(FakeAnalytics(make_analytics()))
    assert service.generate("Other Bank").signals == []
    result = service.generate("Wells Fargo")
    assert all(any("production deployment" in item for item in signal.limitations) for signal in result.signals)
