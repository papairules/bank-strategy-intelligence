import asyncio
from datetime import datetime, timezone

import networkx as nx
import pytest

from backend.app.application.agents.strategy_agent import (
    StrategyAgentResult,
    StrategyAgentStatus,
    StrategyFinding,
)
from backend.app.application.agents.supervisor_agent import (
    EvidenceAssessment,
    SupervisorAppService,
    SupervisorReportRequest,
    SupervisorResponse,
    SupervisorRuntimeError,
    SupervisorRuntimeFailureCode,
)
from backend.app.application.hiring import HiringSignalGenerationResult


class FakeStrategy:
    def __init__(self, organization="Wells Fargo"):
        self.organization = organization
        self.calls = []

    async def answer(self, request):
        self.calls.append(request)
        return StrategyAgentResult(
            status=StrategyAgentStatus.ANSWERED,
            organization=self.organization,
            question=request.question,
            executive_summary="Strategic evidence supports modernization.",
            findings=[StrategyFinding(title="Modernization", statement="Strategic evidence suggests modernization.", support=[])],
            reliability=.7,
            limitations=[],
            tool_calls_used=1,
            provider="fake",
            model="fake",
            agent_version="test",
        )


class FakeHiringSignals:
    def __init__(self, organization="Wells Fargo"):
        self.organization = organization
        self.calls = []

    def generate(self, organization):
        self.calls.append(organization)
        return HiringSignalGenerationResult(
            organization=self.organization,
            generated_at=datetime.now(timezone.utc),
            signals=[],
        )


class FakeKG:
    def __init__(self, total=1610, enriched=5, classified=None, organization="Wells Fargo"):
        self.graph = nx.MultiDiGraph()
        self.graph.graph.update(
            organization=organization,
            jobs_read=total,
            evidence_records_used=total,
            enriched_jobs_used=enriched,
            classified_jobs_used=enriched if classified is None else classified,
            hiring_signals_used=0,
        )
        self.calls = []

    def build_for_organization(self, organization):
        self.calls.append(organization)
        return self.graph


def supervisor_response(company="Wells Fargo"):
    return SupervisorResponse(
        generated_at=datetime.now(timezone.utc).isoformat(),
        company_id="WELLS_FARGO",
        company_name=company,
        question="report",
        mode="report",
        executive_summary="Evidence suggests a modernization focus.",
        evidence_assessment=EvidenceAssessment(sufficient=True, overall_confidence=.6),
        opportunities=[],
        limitations=[],
        answer="Evidence suggests a modernization focus.",
    )


def service(*, strategy=None, hiring=None, kg=None, runner=None):
    return SupervisorAppService(
        strategy_service=strategy or FakeStrategy(),
        hiring_signals=hiring or FakeHiringSignals(),
        hiring_read=object(),
        hiring_kg=kg or FakeKG(),
        supervisor_runner=runner or (lambda request: supervisor_response()),
        enabled=True,
        provider="openai",
        model="test-model",
    )


def test_orchestrates_typed_inputs_and_reports_sparse_coverage():
    captured = []
    result = asyncio.run(
        service(runner=lambda request: captured.append(request) or supervisor_response()).generate_report(
            SupervisorReportRequest(organization="Wells Fargo")
        )
    )
    assert captured[0].strategy_output["organization"] == "Wells Fargo"
    assert captured[0].hiring_output["company"] == "Wells Fargo"
    assert result.coverage.total_jobs == 1610
    assert result.coverage.enriched_jobs == 5
    assert result.coverage.enrichment_coverage_percentage == pytest.approx(.3106)
    assert "directional rather than comprehensive" in result.report.limitations[0]
    assert result.report.organization == "Wells Fargo"


def test_zero_enrichment_is_not_a_hard_failure():
    result = asyncio.run(
        service(kg=FakeKG(total=100, enriched=0)).generate_report(
            SupervisorReportRequest(organization="Wells Fargo")
        )
    )
    assert result.coverage.kg_enriched_job_count == 0
    assert result.kg_summary.observed_technologies == []
    assert result.report.limitations


def test_complete_coverage_removes_obsolete_sparse_warning_and_keeps_total_jobs():
    result = asyncio.run(
        service(kg=FakeKG(total=1610, enriched=1610)).generate_report(
            SupervisorReportRequest(organization="Wells Fargo")
        )
    )

    assert result.coverage.enrichment_coverage_percentage == 100
    assert result.coverage.limitations == []
    assert result.report.total_hiring_jobs == 1610
    assert not any("sparse" in item.casefold() for item in result.report.limitations)


def test_full_capability_classification_without_enrichment_is_reported_separately():
    result = asyncio.run(
        service(kg=FakeKG(total=1120, enriched=0, classified=1120)).generate_report(
            SupervisorReportRequest(organization="Wells Fargo")
        )
    )

    assert result.coverage.enrichment_coverage_percentage == 0
    assert result.coverage.classified_jobs == 1120
    assert result.coverage.classification_coverage_percentage == 100
    assert any(
        "capability classification" in item.casefold() and "1120 of 1120" in item
        for item in result.coverage.limitations
    )


def test_cross_company_question_stops_before_specialists():
    strategy, hiring, kg = FakeStrategy(), FakeHiringSignals(), FakeKG()
    with pytest.raises(SupervisorRuntimeError) as caught:
        asyncio.run(
            service(strategy=strategy, hiring=hiring, kg=kg).generate_report(
                SupervisorReportRequest(
                    organization="Wells Fargo",
                    question="What are Goldman Sachs priorities?",
                )
            )
        )
    assert caught.value.code == SupervisorRuntimeFailureCode.ORGANIZATION_SCOPE_MISMATCH
    assert strategy.calls == hiring.calls == kg.calls == []


def test_specialist_company_contamination_is_rejected_before_supervisor():
    runner_calls = []
    with pytest.raises(SupervisorRuntimeError) as caught:
        asyncio.run(
            service(
                strategy=FakeStrategy("Goldman Sachs"),
                runner=lambda request: runner_calls.append(request) or supervisor_response(),
            ).generate_report(SupervisorReportRequest(organization="Wells Fargo"))
        )
    assert caught.value.code == SupervisorRuntimeFailureCode.ORGANIZATION_SCOPE_MISMATCH
    assert runner_calls == []
