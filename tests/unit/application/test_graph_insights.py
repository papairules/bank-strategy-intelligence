from datetime import date
from uuid import UUID

from backend.app.application.agents.strategy_agent.models import (
    Evidence as StrategyEvidence,
    StrategicSignal,
    StrategyAgentResult,
    StrategyAgentStatus,
)
from backend.app.application.hiring.kg import GraphInsightsService, HiringKnowledgeGraphService
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence, SourceType


def job(job_id, evidence_id, *, organization="Wells Fargo", capability="Software Engineering", technologies=None):
    job_id = UUID(int=job_id)
    evidence_id = UUID(int=evidence_id)
    return JobPosting(
        job_id=job_id,
        evidence_id=evidence_id,
        organization=organization,
        source_job_id=str(job_id),
        title="Platform Engineer",
        description="Build Python services.",
        location="Charlotte, NC",
        country="US",
        posted_date=date(2026, 8, 1),
        source_url=f"https://jobs.example.test/{job_id}",
        capability_classifications=[capability] if capability else [],
        technologies=technologies or [],
    )


def evidence(evidence_id, job_id):
    if isinstance(evidence_id, int):
        evidence_id = UUID(int=evidence_id)
    return Evidence(
        evidence_id=evidence_id,
        source_url=f"https://jobs.example.test/{job_id}",
        source_type=SourceType.CAREER_SITE,
        retrieved_at="2026-08-22T00:00:00Z",
        source_excerpt="Build Python services.",
        collector_identity="test",
    )


class FakeRead:
    def __init__(self, jobs, evidence_records):
        self.jobs = jobs
        self.evidence = {item.evidence_id: item for item in evidence_records}

    def list_jobs_for_analytics(self, organization):
        return list(self.jobs)

    def get_evidence(self, evidence_id):
        return self.evidence.get(evidence_id)

    def get_latest_enrichment(self, job_id):
        return None


class FakeSignals:
    def generate(self, organization):
        from datetime import datetime, timezone

        from backend.app.application.hiring import HiringSignalGenerationResult

        return HiringSignalGenerationResult(organization=organization, generated_at=datetime.now(timezone.utc), signals=[])


class FakeStrategyResearch:
    def __init__(self, cached=None):
        self._cached = cached

    def get_latest_for_organization(self, organization):
        return self._cached


def strategy_result():
    return StrategyAgentResult(
        status=StrategyAgentStatus.ANSWERED,
        organization="Wells Fargo",
        question="Generate a company intelligence report for Wells Fargo.",
        executive_summary="Evidence supports cloud modernization.",
        findings=[],
        reliability=0.7,
        limitations=[],
        tool_calls_used=2,
        provider="openai",
        model="gpt-5.4-mini",
        agent_version="strategy-langgraph-v1",
        strategic_signals=[
            StrategicSignal(
                priority="Cloud modernization",
                direction="increase_investment",
                time_horizon="12 months",
                hypothesis="Investing in cloud modernization.",
                supporting_evidence_ids=["EV_1"],
                confidence=0.65,
                confidence_breakdown={},
                evidence=[
                    StrategyEvidence(
                        evidence_id="EV_1",
                        theme="cloud",
                        signal_type="TECHNOLOGY_ADOPTION",
                        statement="Announced cloud modernization.",
                        source_id="SRC_1",
                        source_url="https://news.example.test/a",
                        source_type="news",
                    )
                ],
            )
        ],
    )


def build_service(*, jobs, strategy_research=None):
    kg = HiringKnowledgeGraphService(
        FakeRead(jobs, [evidence(job.evidence_id, job.job_id) for job in jobs]),
        FakeSignals(),
        strategy_research=strategy_research,
    )
    return GraphInsightsService(kg)


def test_insights_include_top_capabilities_and_technologies_ranked_by_job_count():
    jobs = [
        job(1, 11, capability="Risk and Compliance", technologies=["SQL"]),
        job(2, 12, capability="Risk and Compliance", technologies=["SQL"]),
        job(3, 13, capability="Software Engineering", technologies=["Python"]),
    ]
    service = build_service(jobs=jobs)

    insights = service.get_insights("Wells Fargo")

    assert insights.top_capabilities[0].name == "Risk and Compliance"
    assert insights.top_capabilities[0].job_count == 2
    assert insights.top_technologies[0].name == "SQL"
    assert insights.top_technologies[0].job_count == 2
    assert insights.jobs_read == 3
    assert insights.classified_jobs_used == 3


def test_insights_include_strategic_themes_when_strategy_research_cached():
    jobs = [job(1, 11)]
    service = build_service(jobs=jobs, strategy_research=FakeStrategyResearch((strategy_result(), "2026-08-23T00:00:00+00:00")))

    insights = service.get_insights("Wells Fargo")

    assert len(insights.strategic_themes) == 1
    theme = insights.strategic_themes[0]
    assert theme.name == "Cloud modernization"
    assert theme.direction == "increase_investment"
    assert theme.confidence == 0.65
    assert theme.evidence_count == 1
    assert insights.strategic_themes_used == 1


def test_insights_empty_when_no_strategy_research_available():
    jobs = [job(1, 11)]
    service = build_service(jobs=jobs, strategy_research=None)

    insights = service.get_insights("Wells Fargo")

    assert insights.strategic_themes == []
    assert insights.strategic_themes_used == 0


def test_insights_uses_cached_graph_when_available(tmp_path):
    jobs = [job(1, 11, capability="Risk and Compliance")]
    kg = HiringKnowledgeGraphService(
        FakeRead(jobs, [evidence(11, 1)]), FakeSignals(), graph_directory=tmp_path
    )
    kg.build_for_organization("Wells Fargo")
    read_calls = []
    original_list = kg._read.list_jobs_for_analytics
    kg._read.list_jobs_for_analytics = lambda organization: (read_calls.append(organization) or original_list(organization))

    service = GraphInsightsService(kg)
    insights = service.get_insights("Wells Fargo")

    assert insights.top_capabilities[0].name == "Risk and Compliance"
    assert read_calls == []
