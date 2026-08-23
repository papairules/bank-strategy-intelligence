import asyncio
from datetime import datetime, timedelta, timezone

from backend.app.application.agents.strategy_agent import (
    CachedStrategyAgentService,
    StrategyAgentRequest,
    StrategyAgentResult,
    StrategyAgentStatus,
)


def result(question: str, organization: str = "Wells Fargo") -> StrategyAgentResult:
    return StrategyAgentResult(
        status=StrategyAgentStatus.ANSWERED,
        organization=organization,
        question=question,
        executive_summary=f"Summary for: {question}",
        findings=[],
        reliability=0.5,
        limitations=[],
        tool_calls_used=1,
        provider="openai",
        model="test-model",
        agent_version="strategy-langgraph-v1",
    )


class FakeInner:
    def __init__(self):
        self.calls: list[StrategyAgentRequest] = []

    async def answer(self, request: StrategyAgentRequest) -> StrategyAgentResult:
        self.calls.append(request)
        return result(request.question, request.organization)


class FakeRepository:
    def __init__(self):
        self.store: dict[tuple, tuple[StrategyAgentResult, str]] = {}

    def get(self, *, organization, question_key, time_horizon, provider, model, agent_version):
        return self.store.get((organization, question_key, time_horizon, provider, model, agent_version))

    def save(self, *, organization, question_key, time_horizon, provider, model, agent_version, generated_at, result):
        self.store[(organization, question_key, time_horizon, provider, model, agent_version)] = (result, generated_at)


def make_service(*, inner=None, repository=None, ttl=timedelta(hours=24), clock=None):
    return CachedStrategyAgentService(
        inner or FakeInner(),
        repository or FakeRepository(),
        provider="openai",
        model="test-model",
        agent_version="strategy-langgraph-v1",
        ttl=ttl,
        clock=clock or (lambda: datetime(2026, 8, 23, tzinfo=timezone.utc)),
    )


def test_second_identical_request_is_served_from_cache_without_calling_inner():
    inner = FakeInner()
    repository = FakeRepository()
    service = make_service(inner=inner, repository=repository)
    request = StrategyAgentRequest(organization="Wells Fargo", question="What changed recently?")

    first = asyncio.run(service.answer(request))
    second = asyncio.run(service.answer(request))

    assert len(inner.calls) == 1
    assert first == second


def test_different_question_always_calls_inner():
    inner = FakeInner()
    service = make_service(inner=inner)

    asyncio.run(service.answer(StrategyAgentRequest(organization="Wells Fargo", question="What changed recently?")))
    asyncio.run(service.answer(StrategyAgentRequest(organization="Wells Fargo", question="How are they investing in AI?")))

    assert len(inner.calls) == 2


def test_question_key_is_normalized_for_whitespace_and_case():
    inner = FakeInner()
    service = make_service(inner=inner)

    asyncio.run(service.answer(StrategyAgentRequest(organization="Wells Fargo", question="What changed recently?")))
    asyncio.run(service.answer(StrategyAgentRequest(organization="Wells Fargo", question="  WHAT   CHANGED RECENTLY?  ")))

    assert len(inner.calls) == 1


def test_different_time_horizon_is_a_different_cache_entry():
    inner = FakeInner()
    service = make_service(inner=inner)

    asyncio.run(service.answer(StrategyAgentRequest(organization="Wells Fargo", question="What changed?", time_horizon="12 months")))
    asyncio.run(service.answer(StrategyAgentRequest(organization="Wells Fargo", question="What changed?", time_horizon="24 months")))

    assert len(inner.calls) == 2


def test_expired_cache_entry_triggers_a_fresh_call():
    inner = FakeInner()
    repository = FakeRepository()
    now = datetime(2026, 8, 23, tzinfo=timezone.utc)
    clock_value = {"now": now}
    service = make_service(inner=inner, repository=repository, ttl=timedelta(hours=24), clock=lambda: clock_value["now"])
    request = StrategyAgentRequest(organization="Wells Fargo", question="What changed?")

    asyncio.run(service.answer(request))
    clock_value["now"] = now + timedelta(hours=25)
    asyncio.run(service.answer(request))

    assert len(inner.calls) == 2


def test_different_organization_is_a_different_cache_entry():
    inner = FakeInner()
    service = make_service(inner=inner)

    asyncio.run(service.answer(StrategyAgentRequest(organization="Wells Fargo", question="What changed?")))
    asyncio.run(service.answer(StrategyAgentRequest(organization="BNY", question="What changed?")))

    assert len(inner.calls) == 2
