import asyncio
from datetime import datetime, timedelta, timezone

from backend.app.application.agents.supervisor_agent import (
    CachedSupervisorReportService,
    CompactHiringKGSummary,
    CompanyIntelligenceReport,
    EvidenceAssessment,
    HiringCoverageMetadata,
    SupervisorReportRequest,
    SupervisorReportResult,
    SupervisorResponse,
)


def result(question: str = "report", organization: str = "Wells Fargo") -> SupervisorReportResult:
    return SupervisorReportResult(
        organization=organization,
        strategy_signal_count=0,
        hiring_signal_count=0,
        coverage=HiringCoverageMetadata(
            organization=organization,
            total_jobs=0,
            enriched_jobs=0,
            enrichment_coverage_percentage=0,
            classified_jobs=0,
            classification_coverage_percentage=0,
            kg_enriched_job_count=0,
        ),
        kg_summary=CompactHiringKGSummary(organization=organization, node_count=0, edge_count=0, enriched_jobs_used=0),
        supervisor=SupervisorResponse(
            generated_at=datetime.now(timezone.utc).isoformat(),
            company_id=organization.upper().replace(" ", "_"),
            company_name=organization,
            question=question,
            mode="report",
            executive_summary=f"Summary for: {question}",
            evidence_assessment=EvidenceAssessment(sufficient=True, overall_confidence=0.6),
            opportunities=[],
            limitations=[],
            answer=f"Summary for: {question}",
        ),
        report=CompanyIntelligenceReport(
            organization=organization,
            generated_at=datetime.now(timezone.utc).isoformat(),
            executive_summary=f"Summary for: {question}",
        ),
        provider="openai",
        model="test-model",
    )


class FakeInner:
    def __init__(self):
        self.calls: list[SupervisorReportRequest] = []

    async def generate_report(self, request: SupervisorReportRequest) -> SupervisorReportResult:
        self.calls.append(request)
        return result(request.question or "report", request.organization)


class FakeRepository:
    def __init__(self):
        self.store: dict[tuple, tuple[SupervisorReportResult, str]] = {}

    def get(self, *, organization, question_key, time_horizon, provider, model):
        return self.store.get((organization, question_key, time_horizon, provider, model))

    def save(self, *, organization, question_key, time_horizon, provider, model, generated_at, result):
        self.store[(organization, question_key, time_horizon, provider, model)] = (result, generated_at)


def make_service(*, inner=None, repository=None, ttl=timedelta(hours=24), clock=None):
    return CachedSupervisorReportService(
        inner or FakeInner(),
        repository or FakeRepository(),
        provider="openai",
        model="test-model",
        ttl=ttl,
        clock=clock or (lambda: datetime(2026, 8, 23, tzinfo=timezone.utc)),
    )


def test_second_identical_request_is_served_from_cache_without_calling_inner():
    inner = FakeInner()
    repository = FakeRepository()
    service = make_service(inner=inner, repository=repository)
    request = SupervisorReportRequest(organization="Wells Fargo")

    first = asyncio.run(service.generate_report(request))
    second = asyncio.run(service.generate_report(request))

    assert len(inner.calls) == 1
    assert first == second


def test_different_question_always_calls_inner():
    inner = FakeInner()
    service = make_service(inner=inner)

    asyncio.run(service.generate_report(SupervisorReportRequest(organization="Wells Fargo", question="What changed recently?")))
    asyncio.run(service.generate_report(SupervisorReportRequest(organization="Wells Fargo", question="How are they investing in AI?")))

    assert len(inner.calls) == 2


def test_question_key_is_normalized_for_whitespace_and_case():
    inner = FakeInner()
    service = make_service(inner=inner)

    asyncio.run(service.generate_report(SupervisorReportRequest(organization="Wells Fargo", question="What changed recently?")))
    asyncio.run(service.generate_report(SupervisorReportRequest(organization="Wells Fargo", question="  WHAT   CHANGED RECENTLY?  ")))

    assert len(inner.calls) == 1


def test_different_time_horizon_is_a_different_cache_entry():
    inner = FakeInner()
    service = make_service(inner=inner)

    asyncio.run(service.generate_report(SupervisorReportRequest(organization="Wells Fargo", question="What changed?", time_horizon="12 months")))
    asyncio.run(service.generate_report(SupervisorReportRequest(organization="Wells Fargo", question="What changed?", time_horizon="24 months")))

    assert len(inner.calls) == 2


def test_expired_cache_entry_triggers_a_fresh_call():
    inner = FakeInner()
    repository = FakeRepository()
    now = datetime(2026, 8, 23, tzinfo=timezone.utc)
    clock_value = {"now": now}
    service = make_service(inner=inner, repository=repository, ttl=timedelta(hours=24), clock=lambda: clock_value["now"])
    request = SupervisorReportRequest(organization="Wells Fargo")

    asyncio.run(service.generate_report(request))
    clock_value["now"] = now + timedelta(hours=25)
    asyncio.run(service.generate_report(request))

    assert len(inner.calls) == 2


def test_different_organization_is_a_different_cache_entry():
    inner = FakeInner()
    service = make_service(inner=inner)

    asyncio.run(service.generate_report(SupervisorReportRequest(organization="Wells Fargo")))
    asyncio.run(service.generate_report(SupervisorReportRequest(organization="BNY")))

    assert len(inner.calls) == 2
