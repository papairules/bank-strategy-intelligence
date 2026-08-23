from datetime import date
from uuid import UUID

import pytest

from backend.app.application.agents.strategy_agent.models import (
    Evidence as StrategyEvidence,
    StrategicSignal,
    StrategyAgentResult,
    StrategyAgentStatus,
)
from backend.app.application.hiring.kg import (
    HiringKGEdgeType,
    HiringKGNodeType,
    HiringKnowledgeGraphService,
    concept_node_id,
    get_evidence_for_strategic_theme,
    get_strategic_themes_for_organization,
    organization_node_id,
    strategy_evidence_node_id,
    summarize_hiring_knowledge_graph,
)
from backend.app.domain.hiring import JobPosting
from backend.app.domain.intelligence import Evidence, SourceType


WELLS_JOB_ID = UUID("00000000-0000-0000-0000-000000000101")
WELLS_EVIDENCE_ID = UUID("00000000-0000-0000-0000-000000000011")


def job(organization="Wells Fargo"):
    return JobPosting(
        job_id=WELLS_JOB_ID,
        evidence_id=WELLS_EVIDENCE_ID,
        organization=organization,
        source_job_id="SRC-1",
        title="Platform Engineer",
        description="Build Python services on AWS.",
        location="Charlotte, NC",
        country="US",
        posted_date=date(2026, 8, 1),
        source_url="https://jobs.example.test/1",
    )


def evidence():
    return Evidence(
        evidence_id=WELLS_EVIDENCE_ID,
        source_url="https://jobs.example.test/1",
        source_type=SourceType.CAREER_SITE,
        retrieved_at="2026-08-22T00:00:00Z",
        source_excerpt="Build Python services on AWS.",
        collector_identity="approved_csv_import",
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
        from backend.app.application.hiring import HiringSignalGenerationResult
        from datetime import datetime, timezone

        return HiringSignalGenerationResult(
            organization=organization, generated_at=datetime.now(timezone.utc), signals=[]
        )


class FakeStrategyResearch:
    def __init__(self, cached=None):
        self._cached = cached

    def get_latest_for_organization(self, organization):
        return self._cached


def strategic_signal(
    *,
    priority="Cloud modernization",
    business_unit=None,
    evidence_ids=("EV_1",),
) -> StrategicSignal:
    return StrategicSignal(
        priority=priority,
        business_unit=business_unit,
        direction="increase_investment",
        time_horizon="12 months",
        hypothesis="The bank is investing in cloud modernization.",
        supporting_evidence_ids=list(evidence_ids),
        confidence=0.7,
        confidence_breakdown={"quality": 0.7},
        evidence=[
            StrategyEvidence(
                evidence_id=evidence_id,
                theme="cloud",
                signal_type="TECHNOLOGY_ADOPTION",
                statement="The bank announced a cloud modernization initiative.",
                source_id="SRC_1",
                source_url="https://news.example.test/article",
                source_type="news",
                publication_date="2026-07-01",
            )
            for evidence_id in evidence_ids
        ],
    )


def strategy_result(*, organization="Wells Fargo", signals=None) -> StrategyAgentResult:
    return StrategyAgentResult(
        status=StrategyAgentStatus.ANSWERED,
        organization=organization,
        question="Generate a company intelligence report for Wells Fargo.",
        executive_summary="Evidence supports cloud modernization.",
        findings=[],
        reliability=0.7,
        limitations=[],
        tool_calls_used=3,
        provider="openai",
        model="gpt-5.4-mini",
        agent_version="strategy-langgraph-v1",
        strategic_signals=signals or [strategic_signal()],
    )


def build_graph(*, strategy_research=None, jobs=None):
    jobs = jobs if jobs is not None else [job()]
    service = HiringKnowledgeGraphService(
        FakeRead(jobs, [evidence()]), FakeSignals(), strategy_research=strategy_research
    )
    return service.build_for_organization("Wells Fargo")


def test_no_strategy_research_configured_adds_nothing():
    graph = build_graph(strategy_research=None)

    assert get_strategic_themes_for_organization(graph) == []
    summary = summarize_hiring_knowledge_graph(graph)
    assert summary.strategic_themes_used == 0


def test_no_cached_research_adds_nothing():
    graph = build_graph(strategy_research=FakeStrategyResearch(cached=None))

    assert get_strategic_themes_for_organization(graph) == []


def test_strategic_theme_node_and_organization_edge_are_added():
    cached = (strategy_result(), "2026-08-23T00:00:00+00:00")
    graph = build_graph(strategy_research=FakeStrategyResearch(cached=cached))

    assert get_strategic_themes_for_organization(graph) == ["Cloud modernization"]
    theme_id = concept_node_id(HiringKGNodeType.STRATEGIC_THEME, "Wells Fargo", "Cloud modernization")
    assert theme_id in graph
    assert graph.nodes[theme_id]["direction"] == "increase_investment"
    assert graph.nodes[theme_id]["confidence"] == 0.7
    edge = graph.get_edge_data(organization_node_id("Wells Fargo"), theme_id)[
        HiringKGEdgeType.HAS_STRATEGIC_THEME.value
    ]
    assert edge["derivation_type"] == "cached_strategy_research"
    assert edge["provider"] == "openai"
    assert edge["generated_at"] == "2026-08-23T00:00:00+00:00"
    summary = summarize_hiring_knowledge_graph(graph)
    assert summary.strategic_themes_used == 1


def test_strategy_evidence_nodes_are_linked_and_queryable():
    cached = (strategy_result(signals=[strategic_signal(evidence_ids=("EV_1", "EV_2"))]), "2026-08-23T00:00:00+00:00")
    graph = build_graph(strategy_research=FakeStrategyResearch(cached=cached))

    evidence_ids = get_evidence_for_strategic_theme(graph, "Cloud modernization")
    assert evidence_ids == ["EV_1", "EV_2"]
    node_id = strategy_evidence_node_id("Wells Fargo", "EV_1")
    assert graph.nodes[node_id]["node_type"] == HiringKGNodeType.STRATEGY_EVIDENCE.value
    assert graph.nodes[node_id]["source_url"] == "https://news.example.test/article"


def test_business_unit_cross_link_only_when_matching_node_exists():
    signal_with_bu = strategic_signal(business_unit="Consumer Banking")
    cached = (strategy_result(signals=[signal_with_bu]), "2026-08-23T00:00:00+00:00")
    graph = build_graph(strategy_research=FakeStrategyResearch(cached=cached))

    theme_id = concept_node_id(HiringKGNodeType.STRATEGIC_THEME, "Wells Fargo", "Cloud modernization")
    business_unit_id = concept_node_id(HiringKGNodeType.BUSINESS_UNIT, "Wells Fargo", "Consumer Banking")
    assert not graph.has_edge(theme_id, business_unit_id, HiringKGEdgeType.ABOUT_BUSINESS_UNIT.value)


def test_cross_organization_strategy_research_is_rejected():
    cached = (strategy_result(organization="BNY"), "2026-08-23T00:00:00+00:00")

    with pytest.raises(ValueError, match="another organization's strategy research"):
        build_graph(strategy_research=FakeStrategyResearch(cached=cached))


def test_multiple_themes_are_all_added():
    cached = (
        strategy_result(signals=[strategic_signal(priority="Cloud modernization"), strategic_signal(priority="AI adoption")]),
        "2026-08-23T00:00:00+00:00",
    )
    graph = build_graph(strategy_research=FakeStrategyResearch(cached=cached))

    assert get_strategic_themes_for_organization(graph) == ["AI adoption", "Cloud modernization"]
    summary = summarize_hiring_knowledge_graph(graph)
    assert summary.strategic_themes_used == 2
