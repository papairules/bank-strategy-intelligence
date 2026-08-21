import asyncio
from functools import wraps
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from backend.app.application.agents.registry import AgentToolDefinition, AgentToolRegistry
from backend.app.application.agents.models import AgentToolDomain, OrganizationInput
from backend.app.application.agents.strategy_agent import (
    StrategyAgentError,
    StrategyAgentFailureCode,
    StrategyAgentRequest,
    StrategyAgentService,
    StrategyProviderFinding,
    StrategyProviderOutput,
    StrategyProviderResponse,
    StrategyToolCall,
)


def async_test(function):
    @wraps(function)
    def wrapper():
        return asyncio.run(function())
    return wrapper


class Result(BaseModel):
    organization: str
    evidence_coverage: float = 1
    enrichment_coverage: float = .5
    observation_start: str = "2026-01-01"
    observation_end: str = "2026-01-16"
    limitations: list[str] = []


class Registry(AgentToolRegistry):
    def __init__(self):
        self._definitions = (AgentToolDefinition("strategy.get_context", AgentToolDomain.STRATEGY, "context", True, OrganizationInput, Result),)


class Tools:
    def __init__(self):
        self.calls = []
        self.registry = Registry()
        self.strategy = SimpleNamespace(get_context=self.get_context)
    def get_context(self, request):
        self.calls.append(request)
        return Result(organization=request.organization)


class Provider:
    def __init__(self, plan, output): self.responses = [plan, output]
    async def respond(self, request): return self.responses.pop(0)


def response(**kwargs):
    return StrategyProviderResponse(provider="fake", model="fake", agent_version="v1", **kwargs)


def service(plan_calls=None, findings=None, *, enabled=True, limitations=None):
    plan = response(tool_calls=plan_calls or [])
    output = response(output=StrategyProviderOutput(
        executive_summary="The available evidence suggests a limited observed pattern.",
        findings=findings or [], limitations=limitations or []))
    tools = Tools()
    return StrategyAgentService(tools, Provider(plan, output), enabled=enabled), tools


@async_test
async def test_governed_answer_reconstructs_trusted_support():
    agent, tools = service(
        [StrategyToolCall(call_id="1", name="strategy.get_context", arguments={"organization": "Other"})],
        [StrategyProviderFinding(title="Observed context", statement="The observed hiring data indicates limited coverage.", citation_references=["strategy_ref_1"])],
    )
    result = await agent.answer(StrategyAgentRequest(organization="Wells Fargo", question="What is observed?"))
    assert result.status == "answered"
    assert result.findings[0].support[0].support_class == "derived_analytics"
    assert tools.calls[0].organization == "Wells Fargo"
    assert 0 <= result.reliability <= 1


@async_test
async def test_unknown_tool_is_rejected():
    agent, _ = service([StrategyToolCall(call_id="1", name="evil.run", arguments={})])
    with pytest.raises(StrategyAgentError, match="unapproved") as caught:
        await agent.answer(StrategyAgentRequest(organization="Bank", question="Question?"))
    assert caught.value.code == StrategyAgentFailureCode.INVALID_TOOL_REQUEST


@async_test
async def test_duplicate_calls_are_deduplicated():
    calls = [StrategyToolCall(call_id=str(i), name="strategy.get_context", arguments={}) for i in range(2)]
    agent, tools = service(calls)
    result = await agent.answer(StrategyAgentRequest(organization="Bank", question="Question?"))
    assert result.tool_calls_used == 1
    assert len(tools.calls) == 1


@async_test
async def test_unknown_reference_is_rejected():
    agent, _ = service(
        [StrategyToolCall(call_id="1", name="strategy.get_context", arguments={})],
        [StrategyProviderFinding(title="Finding", statement="The available evidence suggests a pattern.", citation_references=["invented"])],
    )
    with pytest.raises(StrategyAgentError) as caught:
        await agent.answer(StrategyAgentRequest(organization="Bank", question="Question?"))
    assert caught.value.code == StrategyAgentFailureCode.REFERENCE_VALIDATION


@async_test
async def test_unsupported_intent_language_is_rejected():
    agent, _ = service(
        [StrategyToolCall(call_id="1", name="strategy.get_context", arguments={})],
        [StrategyProviderFinding(title="Finding", statement="The bank is investing in AI.", citation_references=["strategy_ref_1"])],
    )
    with pytest.raises(StrategyAgentError) as caught:
        await agent.answer(StrategyAgentRequest(organization="Bank", question="Question?"))
    assert caught.value.code == StrategyAgentFailureCode.CLAIM_VALIDATION


@async_test
async def test_insufficient_evidence_is_successful():
    agent, _ = service(limitations=["Coverage is insufficient."])
    result = await agent.answer(StrategyAgentRequest(organization="Bank", question="Question?"))
    assert result.status == "insufficient_evidence"
    assert result.reliability <= .35


@async_test
async def test_disabled_by_default():
    agent, _ = service(enabled=False)
    with pytest.raises(StrategyAgentError) as caught:
        await agent.answer(StrategyAgentRequest(organization="Bank", question="Question?"))
    assert caught.value.code == StrategyAgentFailureCode.DISABLED
