from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from backend.app.application.evidence import EvidenceSummary, UnifiedEvidenceRecord
from backend.app.application.strategy import (
    CrossDomainStrategicSignalService,
    StrategicSignalThresholds,
    StrategicSignalType,
)
from backend.app.domain.intelligence import SourceType


NOW = datetime(2026, 8, 21, tzinfo=timezone.utc)


def fixture(*, total=10, enriched=5, duplicate_technology_job=False):
    jobs = [uuid4() for _ in range(total)]
    evidence = [uuid4() for _ in range(total)]
    refs = [SimpleNamespace(job_id=jobs[index], evidence_id=evidence[index]) for index in range(total)]
    technology_refs = [refs[0], refs[0], refs[0]] if duplicate_technology_job else refs[:3]
    snapshot = SimpleNamespace(total_active_jobs=total, observation_start=date(2026, 7, 1) if total else None, observation_end=date(2026, 8, 20) if total else None, generated_at=NOW)
    hiring_analytics = SimpleNamespace(
        snapshot=snapshot,
        capability=SimpleNamespace(capabilities=[SimpleNamespace(capability="Data & Analytics", job_count=4, percentage_of_classified_jobs=80, contributing_records=refs[:4])] if total else []),
        geographic=SimpleNamespace(by_city=[SimpleNamespace(value="Charlotte", job_count=4, percentage_of_total=40, contributing_records=refs[:4])] if total else []),
        seniority=SimpleNamespace(leadership_percentage=40, leadership_contributing_records=refs[:4] if total else []),
    )
    hiring_signal_id = uuid4()
    hiring_signals = SimpleNamespace(signals=[SimpleNamespace(title="Observed analytics hiring", score=SimpleNamespace(strength=0.7), signal=SimpleNamespace(signal_id=hiring_signal_id, supporting_evidence_ids=evidence[:4]))] if total else [], generated_at=NOW)
    technology = SimpleNamespace(
        snapshot=SimpleNamespace(total_jobs=total, enriched_jobs=enriched, technology_observation_count=max(enriched * 2, 0)),
        top_technologies=[SimpleNamespace(technology="Python", job_count=3, percentage_of_enriched_jobs=60, contributing_records=technology_refs)] if enriched else [],
    )
    technology_signal_id = uuid4()
    technology_evidence = evidence[:1] if duplicate_technology_job else evidence[:3]
    technology_signals = SimpleNamespace(signals=[SimpleNamespace(signal_id=technology_signal_id, title="Observed Python concentration", strength=0.7, supporting_evidence_ids=technology_evidence)] if enriched else [])
    records = [UnifiedEvidenceRecord(
        evidence_id=evidence[index], organization="Wells Fargo", source="Workday", source_type=SourceType.CAREER_SITE, source_url="https://example.test/job", captured_at=NOW, observed_at=date(2026, 8, 20), job_id=jobs[index], job_title=f"Role {index}", job_location="Charlotte", business_unit="Analytics" if index < 4 else None, enrichment_present=index < enriched, enrichment_provider="provider" if index < enriched else None, technologies=["Python"] if index < (1 if duplicate_technology_job else 3) else [], related_technology_observation_count=1 if index < (1 if duplicate_technology_job else 3) else 0,
    ) for index in range(total)]
    summary = EvidenceSummary(organization="Wells Fargo", total_evidence_records=total, total_jobs=total, jobs_with_evidence=total, evidence_coverage=100 if total else 0, enriched_evidence_count=enriched, enrichment_coverage=enriched / total * 100 if total else 0, evidence_supporting_hiring_signals=min(4, total), evidence_supporting_technology_observations=min(3, total), evidence_supporting_technology_signals=min(3, total), source_distribution=[], observation_start=snapshot.observation_start, observation_end=snapshot.observation_end, generated_at=NOW)
    return hiring_analytics, hiring_signals, technology, technology_signals, summary, records, hiring_signal_id, technology_signal_id


class Hiring:
    def __init__(self, analytics, signals): self._analytics, self._signals = analytics, signals
    def analytics(self, organization): return self._analytics if organization == "Wells Fargo" else fixture(total=0, enriched=0)[0]
    def signals(self, organization): return self._signals if organization == "Wells Fargo" else fixture(total=0, enriched=0)[1]
class Technology:
    def __init__(self, value): self.value = value
    def analytics(self, organization): return self.value if organization == "Wells Fargo" else fixture(total=0, enriched=0)[2]
class TechnologySignals:
    def __init__(self, value): self.value = value
    def generate(self, organization): return self.value if organization == "Wells Fargo" else fixture(total=0, enriched=0)[3]
class Evidence:
    def __init__(self, summary, records): self._summary, self._records = summary, records
    def summary(self, organization): return self._summary if organization == "Wells Fargo" else fixture(total=0, enriched=0)[4]
    def records_for_intelligence(self, organization): return self._records if organization == "Wells Fargo" else []


def service(data, thresholds=None):
    analytics, hiring_signals, technology, technology_signals, summary, records, *_ = data
    return CrossDomainStrategicSignalService(Hiring(analytics, hiring_signals), Technology(technology), TechnologySignals(technology_signals), Evidence(summary, records), thresholds)


def test_empty_and_low_coverage_are_suppressed_with_reasons():
    assert service(fixture(total=0, enriched=0)).generate("Wells Fargo").signals == []
    low = service(fixture(total=19, enriched=1)).generate("Wells Fargo")
    assert low.signals == []
    assert low.coverage_context.enrichment_coverage == 1 / 19
    assert any("reliability threshold" in item for item in low.limitations)


def test_sufficient_independent_support_generates_all_alignment_types():
    result = service(fixture()).generate("Wells Fargo")
    types = {item.signal_type for item in result.signals}
    assert types == set(StrategicSignalType)
    assert all("strategy is" not in item.summary.lower() for item in result.signals)
    assert all("invest" not in item.summary.lower() for item in result.signals)


def test_single_job_duplication_cannot_inflate_contributors():
    result = service(fixture(duplicate_technology_job=True)).generate("Wells Fargo")
    assert result.signals == []


def test_scores_ids_order_and_traceability_are_deterministic_and_deduplicated():
    data = fixture()
    first = service(data).generate("Wells Fargo")
    second = service(data).generate("Wells Fargo")
    assert first == second
    expected_hiring_id, expected_technology_id = data[-2:]
    for signal in first.signals:
        assert 0 <= signal.strength <= 1
        assert 0 <= signal.confidence <= 1
        assert 0 <= signal.evidence_coverage <= 1
        assert len(signal.unique_contributing_job_ids) == len(set(signal.unique_contributing_job_ids))
        assert len(signal.supporting_evidence_ids) == len(set(signal.supporting_evidence_ids))
        assert expected_hiring_id in signal.related_hiring_signal_ids
        assert expected_technology_id in signal.related_technology_signal_ids
        assert signal.limitations


def test_threshold_boundaries_and_organization_isolation():
    data = fixture()
    assert service(data, StrategicSignalThresholds(minimum_enrichment_coverage=0.5)).generate("Wells Fargo").signals
    assert service(data, StrategicSignalThresholds(minimum_enrichment_coverage=0.51)).generate("Wells Fargo").signals == []
    assert service(data).generate("Other Bank").signals == []
