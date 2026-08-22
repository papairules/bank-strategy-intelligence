import asyncio
import threading

import pytest

from backend.app.application.agents.strategy_agent import (
    IntegratedStrategyAgentService,
    StrategyAgentError,
    StrategyAgentRequest,
)
from backend.app.config import HiringSettings


def native_output(*, signals=True):
    evidence = {
        "evidence_id": "EV_001",
        "theme": "Technology Modernization",
        "business_unit": None,
        "signal_type": "INVESTMENT",
        "direction": "increase",
        "statement": "Management said it plans to increase technology investment.",
        "time_horizon": "12 months",
        "source_id": "SRC_001",
        "source_url": "https://example.com/investor-update",
        "source_type": "investor_presentation",
        "publication_date": "2026-07-15",
    }
    strategic_signals = [] if not signals else [{
        "priority": "Technology modernization",
        "business_unit": None,
        "direction": "increase_investment",
        "time_horizon": "12 months",
        "hypothesis": "The company appears likely to increase technology modernization investment.",
        "supporting_evidence_ids": ["EV_001"],
        "confidence": 0.8,
        "confidence_breakdown": {
            "official_source": 0.3,
            "leadership_or_earnings": 0.25,
            "multiple_sources": 0.0,
            "independent_confirmation": 0.15,
            "recency": 0.1,
        },
        "evidence": [evidence],
    }]
    return {
        "company": "Citigroup",
        "question": "What are the priorities?",
        "time_horizon": "12 months",
        "strategic_signals": strategic_signals,
        **({} if signals else {"message": "Insufficient evidence to identify a reliable strategic direction."}),
    }


class FakeGraph:
    def __init__(self, output):
        self.output = output
        self.state = None
        self.thread_id = None

    def invoke(self, state):
        self.state = state
        self.thread_id = threading.get_ident()
        return {
            **state,
            "research_queries": ["query one", "query two"],
            "final_output": self.output,
        }


def test_integrated_adapter_preserves_native_signals_and_uses_worker_thread():
    graph = FakeGraph(native_output())
    service = IntegratedStrategyAgentService(
        graph, enabled=True, model="gpt-test", api_key_configured=True
    )
    main_thread = threading.get_ident()
    result = asyncio.run(service.answer(StrategyAgentRequest(
        organization="Citigroup",
        question="What are the priorities?",
        time_horizon="12 months",
    )))

    assert graph.state["company"] == "Citigroup"
    assert graph.state["time_horizon"] == "12 months"
    assert graph.thread_id != main_thread
    assert result.findings[0].title == "Technology modernization"
    assert result.findings[0].support == []
    assert result.findings[0].statement == result.strategic_signals[0].hypothesis
    assert result.strategic_signals[0].supporting_evidence_ids == ["EV_001"]
    assert result.strategic_signals[0].evidence[0].source_url == "https://example.com/investor-update"
    assert result.reliability == 0.8
    assert result.tool_calls_used == 2
    assert result.provider == "openai"
    assert result.model == "gpt-test"


def test_integrated_adapter_preserves_insufficient_evidence():
    graph = FakeGraph(native_output(signals=False))
    service = IntegratedStrategyAgentService(
        graph, enabled=True, model="gpt-test", api_key_configured=True
    )
    result = asyncio.run(service.answer(StrategyAgentRequest(
        organization="Citigroup", question="Unsupported claim?"
    )))
    assert result.status == "insufficient_evidence"
    assert result.findings == []
    assert result.strategic_signals == []
    assert result.reliability == 0
    assert "Insufficient evidence" in result.executive_summary


def test_openai_settings_are_namespaced(monkeypatch):
    monkeypatch.setenv("BSI_OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("BSI_OPENAI_MODEL", "gpt-test")
    settings = HiringSettings()
    assert settings.openai_api_key == "test-key"
    assert settings.openai_model == "gpt-test"
    assert settings.strategy_agent_provider == "openai_web"


@pytest.mark.parametrize(("selected", "question", "target"), [
    ("Wells Fargo", "What are Goldman Sachs's major AI priorities?", "Goldman Sachs"),
    ("Goldman Sachs", "What are Wells Fargo's technology priorities?", "Wells Fargo"),
    ("BNY", "What are Goldman's automation priorities?", "Goldman Sachs"),
    ("Wells Fargo", "Compare our priorities with BNY Mellon.", "BNY"),
    ("Wells Fargo", "What is Bank of New York Mellon's strategy?", "BNY"),
])
def test_organization_scope_mismatch_rejects_before_graph_invocation(
    selected, question, target
):
    graph = FakeGraph(native_output())
    service = IntegratedStrategyAgentService(
        graph, enabled=True, model="gpt-test", api_key_configured=True
    )

    with pytest.raises(StrategyAgentError) as caught:
        asyncio.run(service.answer(StrategyAgentRequest(
            organization=selected,
            question=question,
        )))

    assert caught.value.code == "organization_scope_mismatch"
    assert selected in str(caught.value)
    assert target in str(caught.value)
    assert graph.state is None
    assert graph.thread_id is None


@pytest.mark.parametrize(("selected", "question"), [
    ("Wells Fargo", "What are the major AI priorities over the next 12 months?"),
    ("Wells Fargo", "What are Wells Fargo's major AI priorities?"),
    ("Goldman Sachs", "What are Goldman's major automation priorities?"),
    ("BNY", "What are Bank of New York Mellon's modernization priorities?"),
])
def test_matching_or_generic_organization_scope_invokes_graph(selected, question):
    graph = FakeGraph(native_output())
    service = IntegratedStrategyAgentService(
        graph, enabled=True, model="gpt-test", api_key_configured=True
    )

    asyncio.run(service.answer(StrategyAgentRequest(
        organization=selected,
        question=question,
    )))

    assert graph.state is not None
    assert graph.state["company"] == selected
